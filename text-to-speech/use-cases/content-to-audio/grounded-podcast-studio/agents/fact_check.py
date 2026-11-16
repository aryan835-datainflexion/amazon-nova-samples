"""Fact-check step — direct GPT-5.6 Sol Converse call.

Reads the run's source-backed claims from DynamoDB and compares them against
the generated script. Produces an informational report; it does not block
synthesis.
"""

import json

import settings
import store
from bedrock_util import converse_json

PROMPT_TEMPLATE = """You are a fact-checker for a podcast script. You are given
a set of source-backed claims and a podcast script. Compare them.

Source-backed claims (JSON):
{facts}

Podcast script (JSON turns):
{script}

Determine:
1. "supported": source-backed claims reflected or mentioned in the script.
2. "missing": source-backed claims that are NOT used in the script.
3. "unsupported_claims": specific factual claims made in the script that are
   NOT backed by the provided claim set (possible hallucinations).

Return ONLY a JSON object with these three keys. Each list item should be a
short human-readable string. No markdown fences, no commentary."""


def check(session, run_id: str, script: list[dict]) -> dict:
    """Return {"supported": [...], "missing": [...], "unsupported_claims": [...]}."""
    facts = store.get_facts(session, run_id)
    prompt = PROMPT_TEMPLATE.format(
        facts=json.dumps(facts, indent=2),
        script=json.dumps(script, indent=2),
    )
    report, _usage = converse_json(session, settings.FACTCHECK_MODEL, prompt)
    # Normalise shape so the UI can rely on the keys existing.
    return {
        "supported": report.get("supported", []) if isinstance(report, dict) else [],
        "missing": report.get("missing", []) if isinstance(report, dict) else [],
        "unsupported_claims": report.get("unsupported_claims", [])
        if isinstance(report, dict)
        else [],
        "fact_count": len(facts),
    }
