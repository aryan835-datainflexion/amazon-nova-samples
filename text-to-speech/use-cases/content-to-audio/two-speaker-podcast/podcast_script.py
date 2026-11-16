"""Writes the podcast script with Amazon Bedrock.

One Converse call produces a JSON array of turns:

    [{"speaker": "host", "text": "..."}, {"speaker": "cohost", "text": "..."}]

Works unchanged with any model in config.MODELS.
"""

import json
import re

from config import AWS_REGION, MAX_TOKENS, TURN_COUNT


def build_prompt(host: str, cohost: str, topic: str | None) -> str:
    """The instruction sent to the model."""
    topic_line = (
        f"The topic for this episode is: {topic}"
        if topic
        else "Pick an interesting and trending technology topic for this episode."
    )

    return f"""You are a podcast script writer for "Polly Podcasts".

Generate a natural, engaging {TURN_COUNT}-turn podcast script alternating between a host and a co-host.

Host name: {host}
Co-host name: {cohost}
{topic_line}

Rules:
- Exactly {TURN_COUNT} turns, alternating: host, cohost, host, cohost.
- Each turn should be 2-4 sentences of natural spoken dialogue.
- In the first turn, the host says "Welcome to Polly Podcasts" and then introduces themselves as "{host}" and introduces "{cohost}".
- Both speakers refer to each other by name at least once.
- Keep it conversational, informative and energetic.
- Do NOT include stage directions, sound effects or annotations.

Return ONLY a valid JSON array of {TURN_COUNT} objects, each with:
- "speaker": either "host" or "cohost"
- "text": the dialogue for that turn

No markdown fences, no explanation, just the array."""


def extract_text(response: dict) -> str:
    """Pull the reply text out of a Converse response.

    Every model in config.MODELS is a reasoning model, and they all return a
    `reasoningContent` block ahead of the `text` block. Indexing content[0]
    gets you the reasoning, not the answer, so scan for the text block.
    """
    blocks = response["output"]["message"]["content"]
    for block in blocks:
        if "text" in block:
            return block["text"]
    raise RuntimeError(
        f"No text block in the model response "
        f"(stopReason={response.get('stopReason')!r}). "
        "If stopReason is max_tokens, raise MAX_TOKENS in config.py."
    )


def parse(text: str) -> list[dict]:
    """Turn raw model output into a validated list of turns.

    The prompt asks for a bare array, and all three models comply, but models
    sometimes wrap the answer in ```json fences or a line of preamble. Tolerate
    both rather than failing on a cosmetic difference.
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
    if len(script) != TURN_COUNT:
        raise RuntimeError(
            f"Expected exactly {TURN_COUNT} turns, got {len(script)}."
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


def generate(
    session, model_id: str, host: str, cohost: str, topic: str | None
) -> tuple[list[dict], dict]:
    """Ask Bedrock for a script and return it with the metered token usage."""
    client = session.client("bedrock-runtime", region_name=AWS_REGION)

    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": build_prompt(host, cohost, topic)}]}],
        # maxTokens is the only field these models accept — see config.MAX_TOKENS.
        inferenceConfig={"maxTokens": MAX_TOKENS},
    )

    # Converse returns the actual tokens charged to the request. Keep this
    # separate from pricing: callers can apply current pricing themselves.
    return parse(extract_text(response)), response["usage"]
