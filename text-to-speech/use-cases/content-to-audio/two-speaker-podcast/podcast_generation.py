"""Turns a script into a single MP3 with Amazon Polly.

Each turn is synthesized separately so it can use a different voice, then the
segments are concatenated. MP3 is a frame-based format, so joining the raw
bytes gives a stream any player decodes sequentially — no ffmpeg needed. There
is no crossfade or gap between speakers.
"""

from time import perf_counter
from xml.sax.saxutils import escape

from config import (
    AWS_REGION,
    CHUNK_SIZE,
    GENERATIVE_ENGINE,
    NEWSCASTER_ENGINE,
    NEWSCASTER_VOICE_IDS,
    OUTPUT_FORMAT,
    SAMPLE_RATE,
)


def list_voices(session, newscaster: bool = False) -> list[dict]:
    """The voices usable for a speaking style, fetched live from Polly.

    Asking DescribeVoices each run means new Polly voices show up without a
    code change, and there's no hardcoded list to go stale.

    Newscaster needs two things: the neural engine (which the API reports) and
    newscaster-tag support (which it doesn't) — see config.NEWSCASTER_VOICE_IDS.
    """
    client = session.client("polly", region_name=AWS_REGION)
    engine = NEWSCASTER_ENGINE if newscaster else GENERATIVE_ENGINE

    voices, token = [], None
    while True:
        response = client.describe_voices(**({"NextToken": token} if token else {}))
        for v in response["Voices"]:
            if engine not in v["SupportedEngines"]:
                continue
            if newscaster and v["Id"] not in NEWSCASTER_VOICE_IDS:
                continue
            voices.append(
                {
                    "id": v["Id"],
                    "name": v["Name"],
                    "lang": v["LanguageCode"],
                    "language": v.get("LanguageName", ""),
                    "gender": v.get("Gender", "Unspecified"),
                }
            )
        token = response.get("NextToken")
        if not token:
            break

    # English first, then by locale. The prompt generates English dialogue, so
    # an English voice should be the easy default; a pt-BR voice reading an
    # English script sounds wrong. Non-English voices are still selectable —
    # pair them with a translated prompt if you want another language.
    return sorted(
        voices, key=lambda v: (not v["lang"].startswith("en"), v["lang"], v["id"])
    )


def _newscaster_ssml(text: str) -> str:
    """Wrap text in the newscaster domain tag.

    Escaping matters: generated dialogue is full of apostrophes and ampersands,
    and unescaped ones make Polly return InvalidSsmlException.
    """
    return f'<speak><amazon:domain name="news">{escape(text)}</amazon:domain></speak>'


def synthesize_turn(
    client, voice_id: str, text: str, newscaster: bool = False
) -> tuple[bytes, int]:
    """Synthesize one turn and return its MP3 bytes and billable characters."""
    if newscaster:
        style = {
            "Engine": NEWSCASTER_ENGINE,
            "TextType": "ssml",
            "Text": _newscaster_ssml(text),
        }
    else:
        style = {
            "Engine": GENERATIVE_ENGINE,
            "TextType": "text",
            "Text": text,
        }

    response = client.synthesize_speech(
        OutputFormat=OUTPUT_FORMAT,
        SampleRate=SAMPLE_RATE,
        VoiceId=voice_id,
        **style,
    )

    stream = response["AudioStream"]
    audio = bytearray()
    try:
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            audio.extend(chunk)
    finally:
        stream.close()

    return bytes(audio), response["RequestCharacters"]


def synthesize(
    session,
    script: list[dict],
    voices: dict[str, str],
    newscaster: bool = False,
    on_turn=None,
) -> tuple[bytes, int]:
    """Synthesize every turn and return the stitched MP3 and billed characters.

    Args:
        script: turns from podcast_script.generate().
        voices: {"host": voice_id, "cohost": voice_id}.
        newscaster: use the newscaster style.
        on_turn: optional callback(index, total, speaker, voice_id, size, seconds)
            called after each turn, for progress reporting.

    Returns:
        The concatenated MP3 bytes and the total RequestCharacters reported by
        Polly across all turns. This is usage only, not a currency estimate.
    """
    client = session.client("polly", region_name=AWS_REGION)
    segments = []
    characters = 0

    for i, turn in enumerate(script, 1):
        speaker = turn["speaker"]
        voice_id = voices[speaker]

        started = perf_counter()
        audio, turn_characters = synthesize_turn(
            client, voice_id, turn["text"], newscaster
        )
        segments.append(audio)
        characters += turn_characters

        if on_turn:
            on_turn(i, len(script), speaker, voice_id, len(audio), perf_counter() - started)

    return b"".join(segments), characters
