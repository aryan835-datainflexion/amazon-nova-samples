"""Source-backed claim extraction — direct GPT-5.6 Luna Converse call.

Reads the sources gathered by the research agent and distils them into
triple-shaped claims, then writes them to DynamoDB (the run's source of truth).
No tools are needed, so this is a single Converse call rather than an agent.
"""

import json

import settings
import store
from bedrock_util import converse_json

PROMPT_TEMPLATE = """You are an information-extraction system for a podcast fact
base. From the sources below, extract the key facts as (subject, predicate,
object) triples. Only extract facts that are explicitly supported by a source.

Each fact must include the exact "source_url" it came from (one of the URLs
below) and a short "type" for the subject (e.g. Person, Organization, Product,
Date, Metric, Event, Place, Concept).

Sources (JSON):
{sources}

Return ONLY a JSON array of objects, each with:
- "subject": the entity the fact is about
- "predicate": the relationship or attribute
- "object": the value / related entity
- "type": subject type
- "source_url": the URL this fact came from

No markdown fences, no commentary — just the JSON array."""


def extract(session, sources: list[dict]) -> list[dict]:
    """Extract triple-shaped source-backed claims from the research sources."""
    prompt = PROMPT_TEMPLATE.format(sources=json.dumps(sources, indent=2))
    facts, _usage = converse_json(session, settings.EXTRACTION_MODEL, prompt)
    if not isinstance(facts, list):
        raise RuntimeError("Claim extraction did not return a JSON array.")
    return facts


def extract_and_store(session, run_id: str, sources: list[dict]) -> list[dict]:
    """Extract claims and persist them to the DynamoDB claim store."""
    facts = extract(session, sources)
    store.put_facts(session, run_id, facts)
    return facts
