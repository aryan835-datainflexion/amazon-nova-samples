"""Turns a script into a single MP3 with Amazon Polly.

Vendored from the ``two-speaker-podcast`` sample so this project is
self-contained. Each turn is synthesized separately so it can use a different
voice, then the segments are concatenated. MP3 is a frame-based format, so
joining the raw bytes gives a stream any player decodes sequentially — no
ffmpeg needed. There is no crossfade or gap between speakers.
"""

from xml.sax.saxutils import escape

import settings


def list_voices(session, newscaster: bool = False) -> list[dict]:
    """The voices usable for a speaking style, fetched live from Polly.

    Newscaster needs two things: the neural engine (which the API reports) and
    newscaster-tag support (which it doesn't) — see settings.NEWSCASTER_VOICE_IDS.
    """
    client = session.client("polly", region_name=settings.POLLY_REGION)
    engine = settings.NEWSCASTER_ENGINE if newscaster else settings.GENERATIVE_ENGINE

    voices, token = [], None
    while True:
        response = client.describe_voices(**({"NextToken": token} if token else {}))
        for v in response["Voices"]:
            if engine not in v["SupportedEngines"]:
                continue
            if newscaster and v["Id"] not in settings.NEWSCASTER_VOICE_IDS:
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

    # English first, then by locale — the prompt generates English dialogue.
    return sorted(
        voices, key=lambda v: (not v["lang"].startswith("en"), v["lang"], v["id"])
    )


def _newscaster_ssml(text: str) -> str:
    """Wrap text in the newscaster domain tag (escaping to avoid InvalidSsmlException)."""
    return f'<speak><amazon:domain name="news">{escape(text)}</amazon:domain></speak>'


def synthesize_turn(
    client, voice_id: str, text: str, newscaster: bool = False
) -> tuple[bytes, int]:
    """Synthesize one turn and return its MP3 bytes and billable characters."""
    if newscaster:
        style = {
            "Engine": settings.NEWSCASTER_ENGINE,
            "TextType": "ssml",
            "Text": _newscaster_ssml(text),
        }
    else:
        style = {
            "Engine": settings.GENERATIVE_ENGINE,
            "TextType": "text",
            "Text": text,
        }

    response = client.synthesize_speech(
        OutputFormat=settings.OUTPUT_FORMAT,
        SampleRate=settings.SAMPLE_RATE,
        VoiceId=voice_id,
        **style,
    )

    stream = response["AudioStream"]
    audio = bytearray()
    try:
        while True:
            chunk = stream.read(settings.CHUNK_SIZE)
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
        script: turns [{"speaker": "host"|"cohost", "text": ...}, ...].
        voices: {"host": voice_id, "cohost": voice_id}.
        newscaster: use the newscaster style.
        on_turn: optional callback(index, total, speaker, voice_id, size, seconds).
    """
    from time import perf_counter

    client = session.client("polly", region_name=settings.POLLY_REGION)
    segments = []
    characters = 0

    for i, turn in enumerate(script, 1):
        speaker = turn["speaker"]
        voice_id = voices[speaker]

        started = perf_counter()
        audio, turn_characters = synthesize_turn(client, voice_id, turn["text"], newscaster)
        segments.append(audio)
        characters += turn_characters

        if on_turn:
            on_turn(i, len(script), speaker, voice_id, len(audio), perf_counter() - started)

    return b"".join(segments), characters
