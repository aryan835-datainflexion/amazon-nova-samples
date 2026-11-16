"""Configuration for the experimental grounded podcast studio.

This sample is self-contained — the Polly synthesis and script-parsing helpers
are vendored into this directory (``polly_audio.py`` / ``bedrock_util.py``), so
there is no dependency on the sibling ``two-speaker-podcast`` sample.

Resource identifiers (gateway URL, table name, knowledge base id, ...) are
written by ``setup_resources.py`` into a ``.env`` file next to this module and
loaded here. Real environment variables take precedence, so you can override
any value without editing the file.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loader (dependency-free)
# ---------------------------------------------------------------------------
_ENV_FILE = Path(__file__).with_name(".env")


def _load_env_file() -> None:
    """Load KEY=VALUE lines from .env without clobbering real env vars."""
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
#
# Polly generative voices are pinned to us-east-1 by the vendored synthesis
# helper (polly_audio.py). AGENT_REGION is where the agent-facing
# services live: Bedrock runtime, the AgentCore Gateway + Web Search, the
# Knowledge Base / S3 Vectors, and DynamoDB. Keep them equal unless a service
# is unavailable in us-east-1 — see the region note in the README.
AGENT_REGION = _env("AGENT_REGION", "us-east-1")

# ---------------------------------------------------------------------------
# Models — all global cross-Region inference profiles
# ---------------------------------------------------------------------------
#
# GPT-5.6 and Claude profiles here are reasoning models that return a
# `reasoningContent` block before the `text` block — the reused
# podcast_script.extract_text() handles that shape.
RESEARCH_MODEL = _env("RESEARCH_MODEL", "global.openai.gpt-5.6-terra")
EXTRACTION_MODEL = _env("EXTRACTION_MODEL", "global.openai.gpt-5.6-luna")
SCRIPT_MODEL = _env("SCRIPT_MODEL", "global.anthropic.claude-sonnet-5")
FACTCHECK_MODEL = _env("FACTCHECK_MODEL", "global.openai.gpt-5.6-sol")

# Only maxTokens is accepted by these profiles; temperature/topP raise
# ValidationException. The budget must also cover reasoning tokens.
MAX_TOKENS = int(_env("MAX_TOKENS", "4096"))

# How many sources the research agent should gather.
SOURCE_COUNT = int(_env("SOURCE_COUNT", "5"))

# Number of dialogue turns (alternating host/cohost).
TURN_COUNT = int(_env("TURN_COUNT", "6"))

# Number of dialogue turns is defined above (TURN_COUNT).

# ---------------------------------------------------------------------------
# Polly — speech synthesis (vendored from the two-speaker podcast sample)
# ---------------------------------------------------------------------------
#
# Polly generative voices exist in only a handful of regions, so the Polly
# client is pinned here rather than using AGENT_REGION.
POLLY_REGION = _env("POLLY_REGION", "us-east-1")

OUTPUT_FORMAT = _env("OUTPUT_FORMAT", "mp3")
SAMPLE_RATE = _env("SAMPLE_RATE", "24000")
CHUNK_SIZE = int(_env("CHUNK_SIZE", "4096"))

# The two speaking styles run on different engines and are mutually exclusive.
GENERATIVE_ENGINE = "generative"   # conversational
NEWSCASTER_ENGINE = "neural"       # newscaster style

# Voices that accept <amazon:domain name="news"> — not discoverable via
# DescribeVoices, so hardcoded (confirmed empirically in the base sample).
NEWSCASTER_VOICE_IDS = frozenset({"Joanna", "Matthew", "Amy", "Lupe"})

# ---------------------------------------------------------------------------
# Provisioned resources (written by setup_resources.py)
# ---------------------------------------------------------------------------
GATEWAY_URL = _env("GATEWAY_URL")            # https://<id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
DDB_TABLE = _env("DDB_TABLE", "podcast-facts")
KNOWLEDGE_BASE_ID = _env("KNOWLEDGE_BASE_ID")
KB_S3_BUCKET = _env("KB_S3_BUCKET")          # data-source bucket (style guides)
KB_VECTOR_BUCKET = _env("KB_VECTOR_BUCKET")  # S3 Vectors bucket
KB_ROLE_ARN = _env("KB_ROLE_ARN")
GATEWAY_ROLE_ARN = _env("GATEWAY_ROLE_ARN")

# Embedding model for the Knowledge Base.
# Amazon Nova Multimodal Embeddings supports 256 / 384 / 1024 / 3072 dims.
EMBEDDING_MODEL_ID = _env(
    "EMBEDDING_MODEL_ID", "amazon.nova-2-multimodal-embeddings-v1:0"
)
EMBEDDING_DIMENSION = int(_env("EMBEDDING_DIMENSION", "1024"))


def require(*names: str) -> None:
    """Fail fast with a clear message if a resource id is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            f"Missing required settings: {', '.join(missing)}. "
            "Run `python setup_resources.py --profile <name>` first, or set the "
            "matching environment variables."
        )
