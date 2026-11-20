"""Converse helpers + script parsing.

The claim-extraction and fact-check steps are single-shot model calls with no
tools, so they call Converse directly instead of using an agent loop.

``extract_text`` and ``parse`` are vendored from the two-speaker podcast
sample so this project has no cross-directory dependency.
"""

import json
import re

import settings


def extract_text(response: dict) -> str:
    """Pull the reply text out of a Converse response.

    The configured models are reasoning models that return a `reasoningContent`
    block ahead of the `text` block, so scan for the text block rather than
    indexing content[0].
    """
    blocks = response["output"]["message"]["content"]
    for block in blocks:
        if "text" in block:
            return block["text"]
    raise RuntimeError(
        f"No text block in the model response "
        f"(stopReason={response.get('stopReason')!r}). "
        "If stopReason is max_tokens, raise MAX_TOKENS in settings.py."
    )


def parse(text: str) -> list[dict]:
    """Turn raw model output into a validated list of podcast turns.

    Tolerates ```json fences and leading/trailing prose.
    """
    text = text.strip()

    fenced = re.search(r"```(?:\w*)\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        script = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model output was not valid JSON: {e}\n{text[:300]}") from e

    if not isinstance(script, list) or not script:
        raise RuntimeError(f"Expected a JSON array of turns, got: {text[:300]}")
    if len(script) != settings.TURN_COUNT:
        raise RuntimeError(
            f"Expected exactly {settings.TURN_COUNT} turns, got {len(script)}."
        )

    for i, turn in enumerate(script, 1):
        if not isinstance(turn, dict):
            raise RuntimeError(f"Turn {i} is not an object: {turn!r}")
        expected_speaker = "host" if i % 2 else "cohost"
        if turn.get("speaker") != expected_speaker:
            raise RuntimeError(
                f"Turn {i} must be spoken by {expected_speaker!r}, "
                f"got {turn.get('speaker')!r}."
            )
        if not isinstance(turn.get("text"), str) or not turn["text"].strip():
            raise RuntimeError(f"Turn {i} has no usable text.")

    return script


def _extract_json(text: str):
    """Pull the first JSON value (array or object) out of model text.

    Tolerates ```json fences and leading/trailing prose.
    """
    text = text.strip()
    fenced = re.search(r"```(?:\w*)\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"Model output was not valid JSON:\n{text[:400]}")


def converse_json(session, model_id: str, prompt: str):
    """Run one Converse call and return parsed JSON plus token usage."""
    client = session.client("bedrock-runtime", region_name=settings.AGENT_REGION)
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": settings.MAX_TOKENS},
    )
    return _extract_json(extract_text(response)), response["usage"]
