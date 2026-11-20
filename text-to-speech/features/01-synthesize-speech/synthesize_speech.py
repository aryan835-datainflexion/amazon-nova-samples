"""Synthesize Speech — Amazon Polly SynthesizeSpeech.

The core Polly call: send text, get an audio stream back synchronously and
write it to a file. This one example covers the knobs most requests use:

    - Engine:       standard | neural | long-form | generative
    - OutputFormat: mp3 | ogg_vorbis | pcm
    - SampleRate:   e.g. 8000, 16000, 22050, 24000
    - TextType:     text | ssml
    - VoiceId:      e.g. Tiffany, Matthew, Danielle, ...

SynthesizeSpeech is synchronous and accepts up to 6,000 characters total, with
no more than 3,000 billed characters. SSML tags do not count as billed
characters. For longer input use the async task API in ../06-async-synthesis/.
See https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html

Requirements:
    - Python 3.10+
    - boto3
    - AWS credentials configured (named profile or environment variables)
    - IAM permission: polly:SynthesizeSpeech

Usage:
    python synthesize_speech.py
    python synthesize_speech.py --text "Hello from Amazon Polly." --voice Matthew
    python synthesize_speech.py --voice Matthew -o matthew.mp3
    python synthesize_speech.py --format ogg_vorbis --sample-rate 24000
    python synthesize_speech.py --text-type ssml \
        --text '<speak>Hello <break time="500ms"/> world.</speak>'
    python synthesize_speech.py --profile my-aws-profile --region us-west-2
"""

import argparse
import shutil
import sys
from contextlib import closing

# Audio formats this example writes. SynthesizeSpeech also supports "json"
# (speech marks) — see ../04-speech-marks/ for that.
AUDIO_FORMATS = ("mp3", "ogg_vorbis", "pcm")
FORMAT_EXTENSIONS = {"mp3": "mp3", "ogg_vorbis": "ogg", "pcm": "pcm"}

DEFAULT_TEXT = (
    "Hello from Amazon Polly. This audio was generated from plain text with a "
    "single synchronous request."
)


def make_client(profile, region):
    """Create a Polly client, letting boto3 resolve credentials from the
    profile or the default credential chain."""
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synthesize text to speech with Amazon Polly.",
    )
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Text (or SSML) to synthesize.")
    parser.add_argument("--voice", default="Tiffany", help="Voice ID (default: Tiffany).")
    parser.add_argument(
        "--engine",
        default="generative",
        choices=("standard", "neural", "long-form", "generative"),
        help="Polly engine (default: generative).",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        default="mp3",
        choices=AUDIO_FORMATS,
        help="Audio output format (default: mp3). pcm is raw, headerless 16-bit LE.",
    )
    parser.add_argument("--sample-rate", default=None, help="Sample rate in Hz, e.g. 24000.")
    parser.add_argument(
        "--text-type",
        default="text",
        choices=("text", "ssml"),
        help="Whether --text is plain text or SSML (default: text).",
    )
    parser.add_argument(
        "--language-code",
        default=None,
        help="Optional LanguageCode for bilingual voices, e.g. en-US.",
    )
    parser.add_argument("-o", "--output", default=None, help="Output filename.")
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output = args.output or f"speech.{FORMAT_EXTENSIONS[args.output_format]}"

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    kwargs = {
        "Text": args.text,
        "TextType": args.text_type,
        "VoiceId": args.voice,
        "Engine": args.engine,
        "OutputFormat": args.output_format,
    }
    if args.sample_rate:
        kwargs["SampleRate"] = args.sample_rate
    if args.language_code:
        kwargs["LanguageCode"] = args.language_code

    print(f"Synthesizing {len(args.text)} characters with {args.voice} ({args.engine})...")

    try:
        client = make_client(args.profile, args.region)
        response = client.synthesize_speech(**kwargs)
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: Polly request failed: {e}")
        sys.exit(1)

    # AudioStream is a streaming body — read it fully and release the connection.
    with closing(response["AudioStream"]) as audio_stream:
        audio = audio_stream.read()
    with open(output, "wb") as f:
        f.write(audio)

    billed = response.get("RequestCharacters", "?")
    print(f"Wrote {output}  (billed characters: {billed}, content-type: {response.get('ContentType')})")
    if args.output_format == "mp3":
        print(f"Play it with: afplay {output}   (macOS)  |  ffplay {output}")
    elif args.output_format == "ogg_vorbis":
        if shutil.which("ffplay"):
            print(f"Play it with: ffplay {output}")
        else:
            print("To play Ogg, install FFmpeg:")
            print("  brew install ffmpeg   # macOS with Homebrew")
            print(f"Then run: ffplay {output}")


if __name__ == "__main__":
    main()
