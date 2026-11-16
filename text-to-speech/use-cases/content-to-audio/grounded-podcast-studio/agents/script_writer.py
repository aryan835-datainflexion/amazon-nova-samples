"""Script-writer agent — Claude Sonnet 5 + Bedrock Knowledge Base.

A Strands agent that writes the two-speaker dialogue. It is grounded by:
  - the extracted source-backed claims (passed in the prompt), and
  - style guides / reference material retrieved from a Bedrock Managed
    Knowledge Base via a local `retrieve_style_guide` tool.

Output reuses the exact turn contract of the base sample
([{"speaker": "host"|"cohost", "text": ...}]) and is validated with the
reused podcast_script.parse().
"""

import json

import boto3
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

import settings
from bedrock_util import parse

# Set by write_script() so the tool honours the caller's boto3 session/profile.
_SESSION: boto3.Session | None = None


@tool
def retrieve_style_guide(query: str) -> str:
    """Retrieve podcast style-guide and reference passages from the knowledge base.

    Use this to check tone, formatting, segment structure, and any reference
    material before and while writing the script.
    """
    settings.require("KNOWLEDGE_BASE_ID")
    session = _SESSION or boto3.Session()
    client = session.client("bedrock-agent-runtime", region_name=settings.AGENT_REGION)
    response = client.retrieve(
        knowledgeBaseId=settings.KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
    )
    passages = [
        r["content"]["text"]
        for r in response.get("retrievalResults", [])
        if "content" in r and "text" in r["content"]
    ]
    return "\n\n---\n\n".join(passages) if passages else "No style guidance found."


SYSTEM_PROMPT = """You are a podcast script writer for "Polly Podcasts". You
only state factual claims supported by the provided source-backed claims."""

PROMPT_TEMPLATE = """Write a natural, engaging {turns}-turn podcast script
alternating between a host and a co-host, on this topic: {topic}

Host name: {host}
Co-host name: {cohost}

Ground every factual statement in these source-backed claims (JSON):
{facts}

{guide_line}Rules:
- Exactly {turns} turns, alternating: host, cohost, host, cohost, ...
- Each turn is 2-4 sentences of natural spoken dialogue.
- In the first turn the host says "Welcome to Polly Podcasts", introduces
  themselves as "{host}", and introduces "{cohost}".
- Both speakers refer to each other by name at least once.
- Use the source-backed claims accurately; do NOT invent facts beyond them.
- No stage directions, sound effects, or annotations.

Return ONLY a JSON array of {turns} objects, each with "speaker"
("host" or "cohost") and "text". No markdown fences, no commentary."""


def write_script(
    session, topic: str, facts: list[dict], host: str, cohost: str
) -> list[dict]:
    """Generate and validate the two-speaker dialogue."""
    global _SESSION
    _SESSION = session

    model = BedrockModel(
        model_id=settings.SCRIPT_MODEL,
        region_name=settings.AGENT_REGION,
        max_tokens=settings.MAX_TOKENS,
    )

    # The Knowledge Base is optional. When KNOWLEDGE_BASE_ID is unset (no
    # reference material provisioned) the agent runs without the retrieve tool
    # and writes from the source-backed claims alone.
    use_kb = bool(settings.KNOWLEDGE_BASE_ID)
    tools = [retrieve_style_guide] if use_kb else []
    guide_line = (
        "First, call retrieve_style_guide to check the required tone and structure.\n\n"
        if use_kb
        else ""
    )

    agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
    result = agent(
        PROMPT_TEMPLATE.format(
            turns=settings.TURN_COUNT,
            topic=topic,
            host=host,
            cohost=cohost,
            facts=json.dumps(facts, indent=2),
            guide_line=guide_line,
        )
    )
    return parse(str(result))
