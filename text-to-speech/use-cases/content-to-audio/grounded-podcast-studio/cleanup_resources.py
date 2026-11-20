#!/usr/bin/env python3
"""Remove AWS resources created by setup_resources.py.

The command is dry-run only unless ``--yes`` is supplied. Resource names are
derived from the same account, Region, and prefix used during setup, so cleanup
also works after a partially completed setup run.
"""

import argparse
import sys
import time

import boto3
from botocore.exceptions import ClientError


def log(message: str) -> None:
    print(f"[cleanup] {message}", flush=True)


def _error_code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def _not_found(error: ClientError) -> bool:
    return _error_code(error) in {
        "404",
        "NoSuchBucket",
        "NoSuchEntity",
        "NotFoundException",
        "ResourceNotFoundException",
    }


def _items(client, operation: str, key: str, **kwargs) -> list[dict]:
    """Collect a nextToken-paginated result list."""
    items: list[dict] = []
    token = None
    while True:
        params = dict(kwargs)
        if token:
            params["nextToken"] = token
        response = getattr(client, operation)(**params)
        items.extend(response.get(key, []))
        token = response.get("nextToken")
        if not token:
            return items


def _wait_until(description: str, condition, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while not condition():
        if time.time() >= deadline:
            raise TimeoutError(f"timed out waiting for {description}")
        time.sleep(3)


def delete_gateway(client, name: str) -> None:
    gateways = _items(client, "list_gateways", "items")
    gateway = next((item for item in gateways if item.get("name") == name), None)
    if not gateway:
        log(f"Gateway {name}: not found")
        return

    gateway_id = gateway["gatewayId"]
    targets = _items(
        client, "list_gateway_targets", "items", gatewayIdentifier=gateway_id
    )
    for target in targets:
        client.delete_gateway_target(
            gatewayIdentifier=gateway_id, targetId=target["targetId"]
        )
        log(f"deleted Gateway target {target['targetId']}")

    if targets:
        def targets_deleted() -> bool:
            try:
                return not _items(
                    client,
                    "list_gateway_targets",
                    "items",
                    gatewayIdentifier=gateway_id,
                )
            except ClientError as error:
                if _not_found(error):
                    return True
                raise

        _wait_until("Gateway targets to be deleted", targets_deleted)

    client.delete_gateway(gatewayIdentifier=gateway_id)
    log(f"deleted Gateway {name}")

    def gateway_deleted() -> bool:
        try:
            client.get_gateway(gatewayIdentifier=gateway_id)
            return False
        except ClientError as error:
            if _not_found(error):
                return True
            raise

    _wait_until("Gateway to be deleted", gateway_deleted)


def delete_knowledge_base(client, name: str) -> None:
    summaries = _items(
        client, "list_knowledge_bases", "knowledgeBaseSummaries"
    )
    knowledge_base = next(
        (item for item in summaries if item.get("name") == name), None
    )
    if not knowledge_base:
        log(f"Knowledge Base {name}: not found")
        return

    knowledge_base_id = knowledge_base["knowledgeBaseId"]
    data_sources = _items(
        client,
        "list_data_sources",
        "dataSourceSummaries",
        knowledgeBaseId=knowledge_base_id,
    )
    for source in data_sources:
        client.delete_data_source(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=source["dataSourceId"],
        )
        log(f"deleted Knowledge Base data source {source['dataSourceId']}")

    if data_sources:
        def data_sources_deleted() -> bool:
            try:
                return not _items(
                    client,
                    "list_data_sources",
                    "dataSourceSummaries",
                    knowledgeBaseId=knowledge_base_id,
                )
            except ClientError as error:
                if _not_found(error):
                    return True
                raise

        _wait_until("Knowledge Base data sources to be deleted", data_sources_deleted)

    client.delete_knowledge_base(knowledgeBaseId=knowledge_base_id)
    log(f"deleted Knowledge Base {name}")

    def knowledge_base_deleted() -> bool:
        try:
            client.get_knowledge_base(knowledgeBaseId=knowledge_base_id)
            return False
        except ClientError as error:
            if _not_found(error):
                return True
            raise

    _wait_until("Knowledge Base to be deleted", knowledge_base_deleted)


def delete_vector_store(client, bucket_name: str, index_name: str) -> None:
    try:
        client.get_index(vectorBucketName=bucket_name, indexName=index_name)
    except ClientError as error:
        if not _not_found(error):
            raise
    else:
        client.delete_index(vectorBucketName=bucket_name, indexName=index_name)
        log(f"deleted S3 Vectors index {index_name}")

        def index_deleted() -> bool:
            try:
                client.get_index(
                    vectorBucketName=bucket_name, indexName=index_name
                )
                return False
            except ClientError as error:
                if _not_found(error):
                    return True
                raise

        _wait_until("S3 Vectors index to be deleted", index_deleted)

    try:
        client.delete_vector_bucket(vectorBucketName=bucket_name)
        log(f"deleted S3 Vectors bucket {bucket_name}")
    except ClientError as error:
        if _not_found(error):
            log(f"S3 Vectors bucket {bucket_name}: not found")
        else:
            raise


def delete_s3_bucket(session, bucket_name: str, region: str) -> None:
    client = session.client("s3", region_name=region)
    try:
        client.head_bucket(Bucket=bucket_name)
    except ClientError as error:
        if _not_found(error):
            log(f"S3 bucket {bucket_name}: not found")
            return
        raise

    bucket = session.resource("s3", region_name=region).Bucket(bucket_name)
    bucket.object_versions.delete()
    bucket.objects.delete()
    bucket.delete()
    log(f"emptied and deleted S3 bucket {bucket_name}")


def delete_table(client, table_name: str) -> None:
    try:
        client.delete_table(TableName=table_name)
    except ClientError as error:
        if _not_found(error):
            log(f"DynamoDB table {table_name}: not found")
            return
        raise
    client.get_waiter("table_not_exists").wait(TableName=table_name)
    log(f"deleted DynamoDB table {table_name}")


def delete_role(client, role_name: str) -> None:
    try:
        inline = client.list_role_policies(RoleName=role_name).get(
            "PolicyNames", []
        )
    except ClientError as error:
        if _not_found(error):
            log(f"IAM role {role_name}: not found")
            return
        raise

    for policy_name in inline:
        client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)

    attached = client.list_attached_role_policies(RoleName=role_name).get(
        "AttachedPolicies", []
    )
    for policy in attached:
        client.detach_role_policy(
            RoleName=role_name, PolicyArn=policy["PolicyArn"]
        )

    client.delete_role(RoleName=role_name)
    log(f"deleted IAM role {role_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--profile", default=None)
    parser.add_argument("-r", "--region", default="us-east-1")
    parser.add_argument("--prefix", default="polly-podcast")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="perform the deletions; without this flag only the plan is shown",
    )
    args = parser.parse_args()

    if not args.prefix.strip() or "/" in args.prefix:
        parser.error("--prefix must be a non-empty resource-name prefix")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    prefix = args.prefix

    names = {
        "Gateway": f"{prefix}-gw"[:48],
        "Knowledge Base": f"{prefix}-kb",
        "S3 Vectors index": f"{prefix}-index",
        "S3 Vectors bucket": f"{prefix}-vectors-{account}",
        "S3 data bucket": f"{prefix}-refs-{account}",
        "DynamoDB table": f"{prefix}-facts",
        "Gateway IAM role": f"{prefix}-gw-role",
        "Knowledge Base IAM role": f"{prefix}-kb-role",
    }

    log(f"account={account} region={args.region} prefix={prefix}")
    for resource_type, name in names.items():
        log(f"would delete {resource_type}: {name}")

    if not args.yes:
        log("dry run only; pass --yes to delete these resources")
        return

    tasks = [
        (
            "AgentCore Gateway",
            lambda: delete_gateway(
                session.client(
                    "bedrock-agentcore-control", region_name=args.region
                ),
                names["Gateway"],
            ),
        ),
        (
            "Bedrock Knowledge Base",
            lambda: delete_knowledge_base(
                session.client("bedrock-agent", region_name=args.region),
                names["Knowledge Base"],
            ),
        ),
        (
            "S3 Vectors",
            lambda: delete_vector_store(
                session.client("s3vectors", region_name=args.region),
                names["S3 Vectors bucket"],
                names["S3 Vectors index"],
            ),
        ),
        (
            "S3 data bucket",
            lambda: delete_s3_bucket(
                session, names["S3 data bucket"], args.region
            ),
        ),
        (
            "DynamoDB table",
            lambda: delete_table(
                session.client("dynamodb", region_name=args.region),
                names["DynamoDB table"],
            ),
        ),
        (
            "Gateway IAM role",
            lambda: delete_role(
                session.client("iam"), names["Gateway IAM role"]
            ),
        ),
        (
            "Knowledge Base IAM role",
            lambda: delete_role(
                session.client("iam"), names["Knowledge Base IAM role"]
            ),
        ),
    ]

    failures: list[str] = []
    for label, task in tasks:
        try:
            task()
        except Exception as error:
            failures.append(label)
            log(f"ERROR deleting {label}: {type(error).__name__}: {error}")

    if failures:
        sys.exit(
            "Cleanup was incomplete. Re-run the command after resolving: "
            + ", ".join(failures)
        )
    log("remote cleanup complete")


if __name__ == "__main__":
    main()
