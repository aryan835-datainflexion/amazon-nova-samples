"""Send text and receive speech concurrently with Amazon Polly."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from aws_sdk_polly.client import AsyncPollyClient
    from aws_sdk_polly.config import AsyncPollyConfig
    from aws_sdk_polly.models import (
        CloseStreamEvent,
        StartSpeechSynthesisStreamActionStream,
        StartSpeechSynthesisStreamActionStreamCloseStreamEvent,
        StartSpeechSynthesisStreamActionStreamTextEvent,
        StartSpeechSynthesisStreamEventStream,
        StartSpeechSynthesisStreamEventStreamAudioEvent,
        StartSpeechSynthesisStreamInput,
        TextEvent,
    )
    from smithy_aws_core.identity import EnvironmentCredentialsResolver
    from smithy_core.aio.interfaces.eventstream import EventPublisher, EventReceiver
    from smithy_http.aio.crt import AWSCRTHTTPClient
except ImportError:
    print(
        "ERROR: Required packages are not installed. "
        "Run: pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)


REGION = os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "us-east-1"
VOICE_ID = "Tiffany"
OUTPUT_FILE = Path("bidi-streaming.mp3")
SIMULATED_INPUT_DELAY_SECONDS = 1
TEXT_CHUNKS = [
    "Amazon Polly receives this text in separate events. ",
    "It can begin returning audio before all the input text is available. ",
    "This is bidirectional streaming.",
]


async def send_text(
    input_stream: EventPublisher[StartSpeechSynthesisStreamActionStream],
) -> None:
    for number, text in enumerate(TEXT_CHUNKS, start=1):
        print(f"Sending text {number}/{len(TEXT_CHUNKS)}: {text}")
        await input_stream.send(
            StartSpeechSynthesisStreamActionStreamTextEvent(
                value=TextEvent(text=text)
            )
        )

        if number < len(TEXT_CHUNKS):
            # This pause simulates text arriving over time. Polly does not
            # require or introduce it.
            await asyncio.sleep(SIMULATED_INPUT_DELAY_SECONDS)

    await input_stream.send(
        StartSpeechSynthesisStreamActionStreamCloseStreamEvent(
            value=CloseStreamEvent()
        )
    )
    await input_stream.close()
    print("Text input closed.")


async def save_audio(
    output_stream: EventReceiver[StartSpeechSynthesisStreamEventStream],
    output_file_path: Path,
) -> int:
    bytes_written = 0
    receiving_audio = False

    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    with output_file_path.open("wb") as output_file:
        async for event in output_stream:
            if isinstance(event, StartSpeechSynthesisStreamEventStreamAudioEvent):
                audio_chunk = event.value.audio_chunk
                if audio_chunk:
                    if not receiving_audio:
                        print("Receiving audio...")
                        receiving_audio = True
                    output_file.write(audio_chunk)
                    bytes_written += len(audio_chunk)

    return bytes_written


async def run(region: str, voice_id: str, output_file: Path) -> None:
    config = await AsyncPollyConfig.resolve(
        endpoint_uri=f"https://polly.{region}.amazonaws.com",
        region=region,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        transport=AWSCRTHTTPClient(),
    )

    async with AsyncPollyClient(config=config) as client:
        stream = await client.start_speech_synthesis_stream(
            input=StartSpeechSynthesisStreamInput(
                engine="generative",
                output_format="mp3",
                sample_rate="24000",
                voice_id=voice_id,
            )
        )
        _, output_stream = await stream.await_output()
        if output_stream is None:
            raise RuntimeError("Polly did not return an output stream.")

        _, bytes_written = await asyncio.gather(
            send_text(stream.input_stream),
            save_audio(output_stream, output_file),
        )

    if bytes_written == 0:
        output_file.unlink(missing_ok=True)
        raise RuntimeError("Polly returned no audio.")

    print(f"Wrote {bytes_written:,} bytes of audio to {output_file}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send text and receive speech with Polly bidirectional streaming."
    )
    parser.add_argument(
        "--region",
        default=REGION,
        help=f"AWS Region (default: {REGION}).",
    )
    parser.add_argument(
        "--voice",
        default=VOICE_ID,
        help=f"Generative voice ID (default: {VOICE_ID}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help=f"MP3 output path (default: {OUTPUT_FILE}).",
    )
    return parser.parse_args()


def validate_environment_credentials() -> None:
    required = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Set the required environment variable(s): {names}.")


def main() -> None:
    args = parse_args()
    try:
        validate_environment_credentials()
        asyncio.run(run(args.region, args.voice, args.output))
    except Exception as error:
        print(f"ERROR: Polly streaming request failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
