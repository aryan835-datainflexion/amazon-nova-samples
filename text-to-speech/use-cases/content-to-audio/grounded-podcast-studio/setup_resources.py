"""One-shot provisioner for the experimental grounded podcast studio.

Creates (idempotently, where possible) everything the demo needs and writes the
resulting identifiers to a `.env` file that `settings.py` loads:

  1. IAM roles      — one for the Knowledge Base, one for the AgentCore Gateway
  2. DynamoDB table — the session fact store
  3. S3             — a data bucket (seeded with reference_material/) + a
                      Vectors bucket and index
  4. Bedrock KB     — Managed KB (VECTOR / S3 Vectors) + S3 data source + ingest
  5. AgentCore      — a Gateway with the managed Web Search connector target

Usage:
    python setup_resources.py --profile <name> [--region us-east-1] [--prefix podcast]

Re-running is safe: existing resources are detected and reused. Some steps
(KB creation, ingestion) take a few minutes.

NOTE on auth: the Gateway is created with IAM (SigV4) inbound auth so the local
agents can call it with the caller's credentials. If your account requires JWT
inbound auth instead, create the Gateway in the console and set GATEWAY_URL in
.env by hand — the rest of this script still applies.
"""

import argparse
import json
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

import settings

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
REFERENCE_DIR = BASE_DIR / "reference_material"

# Single source of truth: settings.py (override via .env / env vars).
EMBEDDING_MODEL_ID = settings.EMBEDDING_MODEL_ID
EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


# ---------------------------------------------------------------------------
# IAM
# ---------------------------------------------------------------------------
def ensure_role(iam, name: str, service_principal: str, policy: dict) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": service_principal},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        arn = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Polly Podcast Studio demo role",
        )["Role"]["Arn"]
        log(f"created IAM role {name}")
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        log(f"reusing IAM role {name}")

    iam.put_role_policy(
        RoleName=name,
        PolicyName=f"{name}-policy",
        PolicyDocument=json.dumps(policy),
    )
    return arn


def kb_policy(
    region: str,
    account: str,
    data_bucket: str,
    vector_bucket: str,
    embedding_model_arns: list[str] | None = None,
) -> dict:
    if embedding_model_arns is None:
        embedding_model_arns = [
            f"arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL_ID}"
        ]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeEmbeddingModel",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": sorted(set(embedding_model_arns)),
            },
            {
                "Sid": "S3DataSource",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{data_bucket}", f"arn:aws:s3:::{data_bucket}/*"],
            },
            {
                "Sid": "S3Vectors",
                "Effect": "Allow",
                "Action": ["s3vectors:*"],
                "Resource": [
                    f"arn:aws:s3vectors:{region}:{account}:bucket/{vector_bucket}",
                    f"arn:aws:s3vectors:{region}:{account}:bucket/{vector_bucket}/*",
                ],
            },
        ],
    }


def gateway_policy() -> dict:
    # The Gateway assumes this role (GATEWAY_IAM_ROLE credential provider) to
    # call the managed Web Search connector.
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                # SAMPLE ONLY: This wildcard grants full AgentCore access.
                # Before testing in a shared environment or deploying to
                # production, restrict the actions and resources to only those
                # strictly necessary for this workload.
                "Action": ["bedrock-agentcore:*"],
                "Resource": ["*"],
            }
        ],
    }


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------
def ensure_table(ddb, name: str) -> None:
    try:
        ddb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
        )
        ddb.get_waiter("table_exists").wait(TableName=name)
        log(f"created DynamoDB table {name}")
    except ddb.exceptions.ResourceInUseException:
        log(f"reusing DynamoDB table {name}")


# ---------------------------------------------------------------------------
# S3 (data bucket + vectors)
# ---------------------------------------------------------------------------
def ensure_bucket(s3, name: str, region: str) -> None:
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=name)
        else:
            s3.create_bucket(
                Bucket=name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        log(f"created S3 bucket {name}")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            log(f"reusing S3 bucket {name}")
        else:
            raise


def upload_reference_material(s3, bucket: str) -> None:
    for path in REFERENCE_DIR.glob("**/*"):
        if path.is_file():
            key = f"documents/{path.relative_to(REFERENCE_DIR)}"
            s3.upload_file(str(path), bucket, key)
            log(f"uploaded s3://{bucket}/{key}")


def ensure_vector_index(s3v, vector_bucket: str, index: str) -> str:
    try:
        s3v.create_vector_bucket(vectorBucketName=vector_bucket)
        log(f"created S3 Vectors bucket {vector_bucket}")
    except ClientError as e:
        if "Conflict" in str(e) or "Exists" in str(e):
            log(f"reusing S3 Vectors bucket {vector_bucket}")
        else:
            raise
    try:
        s3v.create_index(
            vectorBucketName=vector_bucket,
            indexName=index,
            dimension=EMBEDDING_DIMENSION,
            distanceMetric="cosine",
            dataType="float32",
        )
        log(f"created S3 Vectors index {index}")
    except ClientError as e:
        if "Conflict" in str(e) or "Exists" in str(e):
            log(f"reusing S3 Vectors index {index}")
        else:
            raise
    return s3v.get_index(vectorBucketName=vector_bucket, indexName=index)["index"]["indexArn"]


# ---------------------------------------------------------------------------
# Bedrock Knowledge Base
# ---------------------------------------------------------------------------
def find_knowledge_base(bedrock_agent, name: str) -> dict | None:
    """Return the full configuration for an existing named Knowledge Base."""
    next_token = None
    while True:
        request = {"nextToken": next_token} if next_token else {}
        page = bedrock_agent.list_knowledge_bases(**request)
        for summary in page["knowledgeBaseSummaries"]:
            if summary["name"] == name:
                return bedrock_agent.get_knowledge_base(
                    knowledgeBaseId=summary["knowledgeBaseId"]
                )["knowledgeBase"]
        next_token = page.get("nextToken")
        if not next_token:
            return None


def knowledge_base_embedding_model_arn(knowledge_base: dict) -> str | None:
    return (
        knowledge_base.get("knowledgeBaseConfiguration", {})
        .get("vectorKnowledgeBaseConfiguration", {})
        .get("embeddingModelArn")
    )


def ensure_knowledge_base(
    bedrock_agent,
    name,
    role_arn,
    region,
    index_arn,
    data_bucket,
    existing_knowledge_base=None,
):
    if existing_knowledge_base:
        log(f"reusing knowledge base {name}")
        kb_id = existing_knowledge_base["knowledgeBaseId"]
    else:
        kb_id = bedrock_agent.create_knowledge_base(
            name=name,
            roleArn=role_arn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": f"arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL_ID}",
                    "embeddingModelConfiguration": {
                        "bedrockEmbeddingModelConfiguration": {
                            "dimensions": EMBEDDING_DIMENSION,
                            "embeddingDataType": "FLOAT32",
                        }
                    },
                },
            },
            storageConfiguration={
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": {"indexArn": index_arn},
            },
        )["knowledgeBase"]["knowledgeBaseId"]
        log(f"created knowledge base {name} ({kb_id})")

    # Data source
    sources = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
    if sources:
        ds_id = sources[0]["dataSourceId"]
    else:
        ds_id = bedrock_agent.create_data_source(
            knowledgeBaseId=kb_id,
            name=f"{name}-s3",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{data_bucket}",
                    "inclusionPrefixes": ["documents/"],
                },
            },
        )["dataSource"]["dataSourceId"]
        log(f"created data source ({ds_id})")

    bedrock_agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    log("started ingestion job (indexing runs in the background)")
    return kb_id


# ---------------------------------------------------------------------------
# AgentCore Gateway + Web Search
# ---------------------------------------------------------------------------
def _wait_for_gateway(agentcore, gw_id: str, timeout: int = 300) -> dict:
    """Poll until the gateway leaves CREATING/UPDATING (targets can't be added
    while it is transitioning)."""
    deadline = time.time() + timeout
    while True:
        gw = agentcore.get_gateway(gatewayIdentifier=gw_id)
        status = gw.get("status")
        if status in ("FAILED", "DELETING"):
            raise RuntimeError(f"gateway {gw_id} is {status}: {gw.get('statusReasons')}")
        if status not in ("CREATING", "UPDATING"):
            return gw
        if time.time() > deadline:
            raise RuntimeError(f"gateway {gw_id} still {status} after {timeout}s")
        log(f"gateway status {status}; waiting ...")
        time.sleep(5)


def _wait_for_target(agentcore, gw_id: str, target_id: str, timeout: int = 300) -> None:
    """Poll until the gateway target finishes provisioning."""
    deadline = time.time() + timeout
    while True:
        t = agentcore.get_gateway_target(gatewayIdentifier=gw_id, targetId=target_id)
        status = t.get("status")
        if status in ("FAILED",):
            raise RuntimeError(f"target {target_id} FAILED: {t.get('statusReasons')}")
        if status not in ("CREATING", "UPDATING"):
            return
        if time.time() > deadline:
            raise RuntimeError(f"target {target_id} still {status} after {timeout}s")
        log(f"target status {status}; waiting ...")
        time.sleep(5)


def ensure_gateway(agentcore, name: str, role_arn: str) -> str:
    gw_id = None
    for gw in agentcore.list_gateways().get("items", []):
        if gw["name"] == name:
            log(f"reusing gateway {name}")
            gw_id = gw["gatewayId"]
            break
    if gw_id is None:
        resp = agentcore.create_gateway(
            name=name,
            roleArn=role_arn,
            protocolType="MCP",
            authorizerType="AWS_IAM",  # SigV4 inbound; see NOTE at top of file
        )
        gw_id = resp["gatewayId"]
        log(f"created gateway {name} ({gw_id})")

    # Targets can only be added once the gateway is out of CREATING/UPDATING.
    gw = _wait_for_gateway(agentcore, gw_id)
    url = gw["gatewayUrl"]

    # Web Search connector target
    targets = agentcore.list_gateway_targets(gatewayIdentifier=gw_id).get("items", [])
    if any(t["name"] == "web-search-tool" for t in targets):
        log("reusing web-search target")
    else:
        resp = agentcore.create_gateway_target(
            gatewayIdentifier=gw_id,
            name="web-search-tool",
            targetConfiguration={
                "mcp": {
                    "connector": {
                        "source": {"connectorId": "web-search"},
                        "configurations": [{"name": "WebSearch", "parameterValues": {}}],
                    }
                }
            },
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        _wait_for_target(agentcore, gw_id, resp["targetId"])
        log("created web-search target")
    return url


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--profile", default=None)
    ap.add_argument("-r", "--region", default="us-east-1")
    ap.add_argument("--prefix", default="polly-podcast")
    ap.add_argument(
        "--skip-kb",
        action="store_true",
        help="Don't provision the Knowledge Base / reference material. The "
        "script-writer then runs without style-guide retrieval.",
    )
    args = ap.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    region = args.region
    prefix = args.prefix

    data_bucket = f"{prefix}-refs-{account}"
    vector_bucket = f"{prefix}-vectors-{account}"
    vector_index = f"{prefix}-index"
    table_name = f"{prefix}-facts"
    kb_name = f"{prefix}-kb"
    gateway_name = f"{prefix}-gw"[:48]

    iam = session.client("iam")
    s3 = session.client("s3")
    s3v = session.client("s3vectors")
    ddb = session.client("dynamodb")
    bedrock_agent = session.client("bedrock-agent")
    agentcore = session.client("bedrock-agentcore-control")

    log("=== IAM ===")
    gw_role = ensure_role(
        iam, f"{prefix}-gw-role", "bedrock-agentcore.amazonaws.com", gateway_policy()
    )

    log("=== DynamoDB ===")
    ensure_table(ddb, table_name)

    env = {
        "AGENT_REGION": region,
        "DDB_TABLE": table_name,
        "GATEWAY_ROLE_ARN": gw_role,
    }

    if args.skip_kb:
        log("=== Knowledge Base: SKIPPED (--skip-kb) ===")
    else:
        existing_kb = find_knowledge_base(bedrock_agent, kb_name)
        configured_embedding_arn = (
            f"arn:aws:bedrock:{region}::foundation-model/{EMBEDDING_MODEL_ID}"
        )
        embedding_model_arns = [configured_embedding_arn]
        if existing_kb:
            existing_embedding_arn = knowledge_base_embedding_model_arn(existing_kb)
            if existing_embedding_arn:
                embedding_model_arns.append(existing_embedding_arn)
                if existing_embedding_arn != configured_embedding_arn:
                    log(
                        "existing knowledge base uses embedding model "
                        f"{existing_embedding_arn}; preserving it and updating "
                        "the IAM policy to allow ingestion"
                    )

        kb_role = ensure_role(
            iam, f"{prefix}-kb-role", "bedrock.amazonaws.com",
            kb_policy(
                region,
                account,
                data_bucket,
                vector_bucket,
                embedding_model_arns,
            ),
        )

        log("=== S3 ===")
        ensure_bucket(s3, data_bucket, region)
        upload_reference_material(s3, data_bucket)
        index_arn = ensure_vector_index(s3v, vector_bucket, vector_index)

        log("waiting 10s for IAM role propagation before creating the KB ...")
        time.sleep(10)

        log("=== Bedrock Knowledge Base ===")
        kb_id = ensure_knowledge_base(
            bedrock_agent,
            kb_name,
            kb_role,
            region,
            index_arn,
            data_bucket,
            existing_kb,
        )
        env.update(
            {
                "KNOWLEDGE_BASE_ID": kb_id,
                "KB_S3_BUCKET": data_bucket,
                "KB_VECTOR_BUCKET": vector_bucket,
                "KB_ROLE_ARN": kb_role,
            }
        )

    log("=== AgentCore Gateway + Web Search ===")
    env["GATEWAY_URL"] = ensure_gateway(agentcore, gateway_name, gw_role)

    ENV_FILE.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    log(f"wrote {ENV_FILE}")
    log("done. Start the app with:  uvicorn server:app --reload")


if __name__ == "__main__":
    main()
