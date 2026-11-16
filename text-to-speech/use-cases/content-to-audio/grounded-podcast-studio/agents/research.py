"""Research agent — GPT-5.6 Terra + AgentCore Web Search.

A Strands agent whose only tool is the managed Web Search connector on the
AgentCore Gateway (discovered over MCP). It finds credible, recent sources for
a podcast topic and returns them as structured records.
"""

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client

import settings
from bedrock_util import _extract_json

SYSTEM_PROMPT = """You are a research assistant for a podcast production team.
Use the web search tool to find high-quality, recent, credible sources about
the given topic. Prefer primary sources, reputable publications, and current
information. Read the returned snippets and capture the key facts."""

TASK_TEMPLATE = """Research this podcast topic and gather {n} strong sources: {topic}

Use the web search tool as many times as needed. When you are done, respond
with ONLY a JSON array of exactly {n} objects, each with:
- "title": the source title
- "url": the source URL
- "publishedDate": ISO date if known, else ""
- "snippet": 2-3 sentences summarizing the key facts from that source

No markdown fences, no commentary — just the JSON array."""


def _web_search_client() -> MCPClient:
    """MCP client for the AgentCore Gateway, signed with the caller's IAM creds."""
    settings.require("GATEWAY_URL")
    return MCPClient(
        lambda: aws_iam_streamablehttp_client(
            endpoint=settings.GATEWAY_URL,
            aws_region=settings.AGENT_REGION,
            aws_service="bedrock-agentcore",
        )
    )


def research(topic: str, source_count: int | None = None) -> list[dict]:
    """Return a list of source dicts for the topic."""
    n = source_count or settings.SOURCE_COUNT
    model = BedrockModel(
        model_id=settings.RESEARCH_MODEL,
        region_name=settings.AGENT_REGION,
        max_tokens=settings.MAX_TOKENS,
    )

    with _web_search_client() as client:
        tools = client.list_tools_sync()
        agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
        result = agent(TASK_TEMPLATE.format(n=n, topic=topic))

    sources = _extract_json(str(result))
    if not isinstance(sources, list):
        raise RuntimeError("Research agent did not return a JSON array of sources.")
    return sources


if __name__ == "__main__":
    import sys

    topic = " ".join(sys.argv[1:]) or "the future of quantum computing"
    for s in research(topic):
        print(f"- {s.get('title')} ({s.get('url')})")
