"""Amazon Polly quickstart: explain engines, list voices, and synthesize speech.

This is the first script to run in this repository. It walks through the core
of Amazon Polly's text-to-speech workflow in five steps:

    1. Explain the four speech engines and what each is good for.
    2. Call DescribeVoices to discover which voices exist in your Region.
    3. Validate that your chosen voice supports your chosen engine.
    4. Call SynthesizeSpeech to turn TEXT into audio.
    5. Save the audio, and optionally play it back.

Everything you would normally change lives in the CONFIG block below. The
functions underneath take explicit arguments (rather than reading globals), so
you can import and reuse them in your own scripts and in the other examples in
this repository.

Run it with:  python polly_quickstart.py
"""

from contextlib import closing
from pathlib import Path
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from playsound3 import playsound

# --------------------------------------------------------------------------- #
# CONFIG — edit these values, then re-run the script.
# --------------------------------------------------------------------------- #
# The text you want Polly to speak. The synchronous SynthesizeSpeech API used
# here accepts up to 3,000 billed characters per call; for longer content use
# the asynchronous start_speech_synthesis_task API, which writes to Amazon S3.
TEXT = "Hello, welcome to this demonstration of Amazon Polly."

# Which engine and voice to use. Run the script once to print the voices
# available in your Region, then pick a compatible ENGINE / VOICE_ID pair.
ENGINE = "generative"
VOICE_ID = "Tiffany"

# Audio container to request: "mp3", "ogg_vorbis", or "pcm".
OUTPUT_FORMAT = "mp3"

# Where to write the generated audio file.
OUTPUT_DIRECTORY = Path("audio_output")

# Set to True to play the audio after saving (MP3 only). Off by default so the
# script stays quiet in shared or headless environments.
PLAY_AUDIO = False

# --------------------------------------------------------------------------- #
# Reference data — describes Polly's engines and maps formats to file suffixes.
# --------------------------------------------------------------------------- #
# Polly offers four engines. They differ in naturalness, cost, and which voices
# support them; availability also varies by AWS Region.
ENGINE_DESCRIPTIONS = {
    "standard": "Broad voice availability for cost-effective, general-purpose speech.",
    "neural": "More natural speech for customer-facing and conversational audio.",
    "long-form": "Optimized for longer content such as articles and training material.",
    "generative": "The most expressive, conversational delivery for supported voices.",
}

# SynthesizeSpeech returns raw audio bytes; we choose the file suffix ourselves.
# These are common examples, not the full list — Polly also supports formats
# such as "json" (for speech marks). See the SynthesizeSpeech API reference.
FORMAT_EXTENSIONS = {
    "mp3": ".mp3",
    "ogg_vorbis": ".ogg",
    "pcm": ".pcm",
}


def describe_engines() -> None:
    """Print each Amazon Polly engine and what it is best suited for."""
    print("Amazon Polly engines")
    print("-" * 20)
    for engine, description in ENGINE_DESCRIPTIONS.items():
        print(f"  {engine:<12} {description}")


def list_voices(polly: Any, engine: Optional[str] = None) -> list[dict[str, Any]]:
    """Return the voices available in the current Region.

    DescribeVoices returns results one page at a time. We follow ``NextToken``
    until every page has been collected. Pass ``engine`` to keep only the
    voices that support a given engine, which makes the printed list shorter and
    easier to choose from.
    """
    voices: list[dict[str, Any]] = []
    next_token: Optional[str] = None

    while True:
        # NextToken can't be passed as None on the first call, so build kwargs.
        kwargs = {"NextToken": next_token} if next_token else {}
        response = polly.describe_voices(**kwargs)
        voices.extend(response.get("Voices", []))
        next_token = response.get("NextToken")
        if not next_token:
            break

    if engine is not None:
        voices = [v for v in voices if engine in v.get("SupportedEngines", [])]

    voices.sort(key=lambda voice: (voice["LanguageCode"], voice["Id"]))

    heading = f"Voices supporting the {engine!r} engine" if engine else "Available voices"
    print(f"\n{heading} ({len(voices)}):")
    for voice in voices:
        print(
            f"  {voice['Id']:<18} "
            f"{voice['LanguageCode']:<8} "
            f"{voice['Gender']}"
        )

    return voices


def synthesize_speech(
    polly: Any,
    text: str,
    voice_id: str,
    engine: str,
    output_format: str,
    text_type: str = "text",
) -> tuple[bytes, int]:
    """Synthesize ``text`` and return ``(audio_bytes, character_count)``.

    ``text_type`` defaults to ``"text"`` for plain text; pass ``"ssml"`` to send
    SSML markup instead. ``AudioStream`` is a streaming body, so we wrap it in
    ``closing`` to release the underlying connection once we've read all bytes.
    """
    response = polly.synthesize_speech(
        Text=text,
        VoiceId=voice_id,
        Engine=engine,
        OutputFormat=output_format,
        TextType=text_type,
    )

    with closing(response["AudioStream"]) as audio_stream:
        audio = audio_stream.read()

    # RequestCharacters reports how many characters Polly billed for this call.
    return audio, response["RequestCharacters"]


def save_audio(audio: bytes, output_path: Path) -> Path:
    """Write ``audio`` to ``output_path`` and return the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)
    print(f"Saved {len(audio)} bytes to {output_path.resolve()}")
    return output_path


def play_audio(output_path: Path) -> None:
    """Play a saved MP3 file through the system audio backend."""
    if output_path.suffix.lower() != ".mp3":
        print("Playback helper supports MP3 files only; the audio was still saved.")
        return

    playsound(output_path)


def main() -> None:
    """Run the full quickstart using the values in the CONFIG block."""
    # Step 1: explain the engines before touching AWS.
    describe_engines()

    # Fail early on obvious config typos, with a message that lists valid values.
    if ENGINE not in ENGINE_DESCRIPTIONS:
        raise SystemExit(
            f"ENGINE must be one of {', '.join(ENGINE_DESCRIPTIONS)}; got {ENGINE!r}."
        )
    if OUTPUT_FORMAT not in FORMAT_EXTENSIONS:
        raise SystemExit(
            f"OUTPUT_FORMAT must be one of {', '.join(FORMAT_EXTENSIONS)}; "
            f"got {OUTPUT_FORMAT!r}."
        )

    try:
        # The client picks up credentials and Region from your environment
        # (AWS SSO, a profile, or environment variables) — never hard-code them.
        # To pin a Region instead, pass it explicitly, e.g.:
        #     polly = boto3.client("polly", region_name="us-east-1")
        polly = boto3.client("polly")

        # Step 2: list the voices that support ENGINE in this Region. Filtering
        # by engine keeps the printed list short and easy to choose from.
        voices = list_voices(polly, engine=ENGINE)

        # Step 3: confirm the configured VOICE_ID is one of those voices, so we
        # fail with a clear message instead of an API error at synthesis time.
        if not any(voice["Id"] == VOICE_ID for voice in voices):
            raise ValueError(
                f"Voice {VOICE_ID!r} does not support the {ENGINE!r} engine in "
                "this Region. Choose a voice from the list above."
            )

        # Step 4: synthesize the speech.
        audio, character_count = synthesize_speech(
            polly, TEXT, VOICE_ID, ENGINE, OUTPUT_FORMAT
        )
        print(
            f"\nSynthesized {character_count} characters with "
            f"{VOICE_ID} ({ENGINE}, {OUTPUT_FORMAT})."
        )

        # Step 5: save, then optionally play.
        extension = FORMAT_EXTENSIONS[OUTPUT_FORMAT]
        output_path = OUTPUT_DIRECTORY / f"{ENGINE}_{VOICE_ID}{extension}"
        save_audio(audio, output_path)

        if PLAY_AUDIO:
            play_audio(output_path)
    except (BotoCoreError, ClientError) as error:
        raise SystemExit(f"Amazon Polly request failed: {error}") from error
    except ValueError as error:
        raise SystemExit(f"Configuration error: {error}") from error


if __name__ == "__main__":
    main()
