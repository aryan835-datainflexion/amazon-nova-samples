# Grounded Podcast Studio

> **Status: Experimental.** This sample provisions multiple AWS resources and
> presents an informational fact-check report. It does not currently revise or
> block unsupported claims before speech synthesis.

Producing a fluent podcast script is easy; showing where its claims came from
and reviewing unsupported statements is harder. This solution matters when the
content should be based on current sources, retain a traceable research record,
follow shared editorial guidance, and expose each production stage for human
review.

The studio separates research, claim extraction, grounded writing, review, and
speech synthesis instead of asking one model to perform the entire workflow in
a single prompt. This improves visibility and auditability, but it does not turn
extracted claims into independently verified facts.

An interactive localhost demo that turns a topic into a source-grounded,
two-speaker podcast episode through a visual workflow. It extends the
[`two-speaker-podcast`](../two-speaker-podcast/) CLI sample with research,
source-backed claim extraction, Knowledge Base retrieval, an informational
fact-check report, persistence, and a browser UI.

You enter a topic, and a browser UI walks you through five stages live:

| Stage | Implementation | Model | AWS services |
|---|---|---|---|
| **Research** | Strands agent with a web-search tool | GPT-5.6 Terra | AgentCore Gateway + **Web Search** |
| **Claim extraction** | Direct Bedrock Converse call | GPT-5.6 Luna | **DynamoDB** (claim store) |
| **Script writer** | Strands agent with optional retrieval | Claude Sonnet 5 | **Bedrock Managed Knowledge Base** (S3 Vectors) |
| **Fact check** | Direct Bedrock Converse call | GPT-5.6 Sol | DynamoDB |
| **Speech synthesis** | Deterministic application code | — | **Amazon Polly** |

All models are Bedrock `global.` cross-Region inference profiles. The research
and script-writing stages use [Strands](https://strandsagents.com); claim
extraction and fact checking use direct Converse calls. The workflow runs
locally with your AWS credentials (SigV4) — nothing is deployed to AgentCore
Runtime.

## Architecture

```
Browser (static/) ──SSE──▶ FastAPI (server.py) ──▶ orchestrator.py
                                                        │
   research → claim extraction → script → fact-check → synthesis
      │            │           │          │           │
 AgentCore     DynamoDB    Bedrock KB   DynamoDB    Amazon Polly
 Web Search    (claims)    (S3 Vectors) (claims)    (reused module)
```

The DynamoDB table is the deterministic source of truth for a run's
source-backed claims;
AgentCore Memory is intentionally **not** used (its long-term extraction is
async and semantic — wrong for exact per-run fact comparison).

## Prerequisites

- Python 3.10+ (the commands below use Python 3.12)
- AWS credentials with access to Bedrock, Polly, DynamoDB, S3, S3 Vectors,
  IAM, and Bedrock AgentCore. Sign in however you normally do (e.g.
  `aws sso login --profile <name>`).
- Model access enabled in the Bedrock console for the four inference profiles
  above and the `amazon.nova-2-multimodal-embeddings-v1:0` embedding model
  (used by the KB).

## Setup

```bash
cd text-to-speech/use-cases/content-to-audio/grounded-podcast-studio
python3.12 --version
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Provision AWS resources and write ./.env
python setup_resources.py --region us-east-1

# Optional: use a named AWS profile
python setup_resources.py --profile <name> --region us-east-1

# ...or skip the Knowledge Base entirely (no reference material):
python setup_resources.py --skip-kb
```

The setup uses boto3's standard credential chain. Omit `--profile` when your
default credentials are correct. To use a named AWS IAM Identity Center (SSO)
profile, sign in with `aws sso login --profile <name>` and pass the same profile
to `setup_resources.py`.

Re-running setup preserves an existing Knowledge Base and grants its actual
embedding model in the IAM policy. Therefore, a Knowledge Base created with an
older model continues using that model. Run `cleanup_resources.py --yes` and
provision again only when you intentionally want to recreate it with the
currently configured embedding model.

### Running without the Knowledge Base

The Knowledge Base is **optional**. With `--skip-kb`, setup provisions only the
DynamoDB table, the Gateway + Web Search, and IAM — no S3 buckets, vector
index, or KB — and leaves `KNOWLEDGE_BASE_ID` unset in `.env`. The script-writer
then runs without the `retrieve_style_guide` tool and writes from the extracted
claims alone. Everything else (research, claim extraction, fact-check,
synthesis) is unchanged. Add reference material and full grounding later by
re-running setup without the flag.

`setup_resources.py` creates two IAM roles, a DynamoDB table, an S3 data bucket
(seeded with `reference_material/`), an S3 Vectors bucket + index, a Bedrock
Managed Knowledge Base with an S3 data source (and starts ingestion), and an
AgentCore Gateway with the managed Web Search target. It writes all identifiers
to `.env`, which `settings.py` loads. Re-running is safe.

> **Auth note:** the Gateway is created with IAM (SigV4) inbound auth so the
> local agents authenticate with your credentials. If your account mandates JWT
> inbound auth, create the Gateway in the console and set `GATEWAY_URL` in
> `.env` by hand.

## Run

```bash
# run through the venv's interpreter so it uses the installed deps
# (a bare `uvicorn` may resolve to a system/Homebrew one without boto3)
source .venv/bin/activate
python -m uvicorn server:app --reload

# Optional: use a named AWS profile
AWS_PROFILE=<name> python -m uvicorn server:app --reload
```

Open <http://localhost:8000>, enter a topic, pick host/co-host voices, and click
**Generate episode**. Each node lights up as it runs and expands to show its
output; the finished MP3 appears in an audio player at the bottom.

## Smoke-test the pieces

```bash
python -m agents.research "the future of quantum computing"   # sources
```

`GET /voices` returns the live Polly voice list (reused from the base sample).

## Region

Polly generative voices are pinned to `us-east-1` via `POLLY_REGION` in the
vendored synthesis module (`polly_audio.py`). `AGENT_REGION` (in `.env`) is
where the agent-facing services live. Keep
them equal unless AgentCore Web Search or S3 Vectors is unavailable in
`us-east-1` — then set `AGENT_REGION` to a supported region (e.g. `us-west-2`)
and re-run setup; synthesis stays in `us-east-1`.

## Layout

```
settings.py            configuration + .env loader
polly_audio.py         Amazon Polly synthesis + voice discovery (vendored, self-contained)
bedrock_util.py        Converse → JSON helper + script parsing (vendored)
store.py               DynamoDB claim store + per-run stage artifacts
agents/                research/script agents + extraction/fact-check model calls
orchestrator.py        runs the 5 stages, persists each, yields SSE events
server.py              FastAPI: /, /voices, /stream (SSE), /audio, /history, /run/{id}
static/                index.html · app.js · styles.css (workflow UI + history pane)
reference_material/    style guides ingested into the Knowledge Base
setup_resources.py     one-shot AWS provisioner → writes .env
cleanup_resources.py   dry-run-by-default teardown for provisioned AWS resources
```

## Teardown

Preview the resources that will be removed:

```bash
python cleanup_resources.py --region us-east-1
```

Delete them after reviewing the plan:

```bash
python cleanup_resources.py --region us-east-1 --yes

# Optional: use a named AWS profile
python cleanup_resources.py --profile <name> --region us-east-1 --yes
```

The cleanup script targets only resources derived from `--prefix` (default:
`polly-podcast`) and handles partially completed setup runs. Local `.env` and
generated `_audio/` files are retained; delete them manually when no longer
needed.

[Back to Content-to-Audio Use Cases](../README.md)
