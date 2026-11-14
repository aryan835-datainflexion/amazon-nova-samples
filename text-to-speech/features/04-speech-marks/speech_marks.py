"""Speech Marks — Amazon Polly SynthesizeSpeech with OutputFormat=json.

Speech marks are metadata about the synthesized audio: the timing of each word
and sentence, viseme (mouth-shape) cues for lip-sync, and the location of SSML
<mark> tags. Request them by setting OutputFormat=json and one or more
SpeechMarkTypes. Polly returns newline-delimited JSON, one object per mark.

    - word     : start/end byte + time offset of each word
    - sentence : same, per sentence
    - viseme   : mouth-shape cues for animation / lip-sync
    - ssml     : positions of <mark> tags in SSML input

This example saves the raw marks to a text file and prints them as a readable
table. Pass --with-audio to also make a second call that writes the matching
mp3, so captions line up with playback.
See https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html

Requirements:
    - Python 3.10+
    - boto3
    - AWS credentials configured (named profile or environment variables)
    - IAM permission: polly:SynthesizeSpeech

Usage:
    python speech_marks.py
    python speech_marks.py --mark-types viseme --text "Hello there."
    python speech_marks.py --mark-types ssml --text-type ssml \
        --text '<speak>Hello <mark name="example"/> world.</speak>'
    python speech_marks.py --with-audio
"""

import argparse
import json
import sys
from contextlib import closing

DEFAULT_TEXT = "Mary had a little lamb. Its fleece was white as snow."


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def parse_args():
    parser = argparse.ArgumentParser(description="Get Amazon Polly speech marks.")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Text to analyze.")
    parser.add_argument(
        "--mark-types",
        nargs="+",
        default=["word", "sentence"],
        choices=["word", "sentence", "viseme", "ssml"],
        help="One or more speech mark types (default: word sentence).",
    )
    parser.add_argument("--voice", default="Matthew", help="Voice ID (default: Matthew).")
    parser.add_argument(
        "--engine",
        default="neural",
        choices=("standard", "neural", "long-form"),
        help="Polly engine (default: neural). Speech marks do not currently support generative.",
    )
    parser.add_argument(
        "--text-type",
        default="text",
        choices=("text", "ssml"),
        help="text or ssml (ssml required for the 'ssml' mark type).",
    )
    parser.add_argument(
        "--marks-output",
        default=None,
        help="Speech marks text file (default: based on the requested mark types).",
    )
    parser.add_argument("--with-audio", action="store_true", help="Also synthesize matching mp3.")
    parser.add_argument(
        "-o",
        "--output",
        default="speech-marks.mp3",
        help="Audio filename for --with-audio (default: speech-marks.mp3).",
    )
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    return parser.parse_args()


def parse_marks(raw_bytes):
    """Polly returns marks as newline-delimited JSON — one object per line."""
    marks = []
    for line in raw_bytes.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            marks.append(json.loads(line))
    return marks


def default_marks_output(mark_types, with_audio):
    mark_names = "-".join(mark_types)
    audio_suffix = "-with-audio" if with_audio else ""
    return f"speech-marks-{mark_names}{audio_suffix}.txt"


def main():
    args = parse_args()

    if len(args.mark_types) > 4:
        print("ERROR: Choose no more than four speech mark types.")
        sys.exit(2)
    if len(set(args.mark_types)) != len(args.mark_types):
        print("ERROR: Each speech mark type can be requested only once.")
        sys.exit(2)
    if "ssml" in args.mark_types and args.text_type != "ssml":
        print("ERROR: The 'ssml' mark type requires --text-type ssml.")
        sys.exit(2)

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    common = {
        "Text": args.text,
        "TextType": args.text_type,
        "VoiceId": args.voice,
        "Engine": args.engine,
    }
    marks_output = args.marks_output or default_marks_output(
        args.mark_types, args.with_audio
    )

    try:
        client = make_client(args.profile, args.region)
        marks_response = client.synthesize_speech(
            OutputFormat="json",
            SpeechMarkTypes=args.mark_types,
            **common,
        )
        with closing(marks_response["AudioStream"]) as marks_stream:
            raw_marks = marks_stream.read()
        marks = parse_marks(raw_marks)

        audio = None
        if args.with_audio:
            audio_response = client.synthesize_speech(OutputFormat="mp3", **common)
            with closing(audio_response["AudioStream"]) as audio_stream:
                audio = audio_stream.read()
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: Polly request failed: {e}")
        sys.exit(1)

    with open(marks_output, "wb") as f:
        f.write(raw_marks)

    print(f"{len(marks)} speech mark(s) for types {args.mark_types}:\n")
    print(f"{'time(ms)':>9}  {'type':<9}{'start':>7}{'end':>7}  {'value / info'}")
    print("-" * 76)
    for m in marks:
        # Word, sentence, and SSML marks include byte offsets. Viseme marks do
        # not, so show a dash in those columns.
        start = m.get("start", "-")
        end = m.get("end", "-")
        info = m.get("value")
        if info is None:
            info = json.dumps(
                {
                    k: v
                    for k, v in m.items()
                    if k not in ("time", "type", "start", "end")
                }
            )
        print(
            f"{m.get('time', 0):>9}  "
            f"{m.get('type', ''):<9}"
            f"{start:>7}"
            f"{end:>7}  "
            f"{info}"
        )
    print(f"\nWrote raw speech marks: {marks_output}")

    if audio is not None:
        with open(args.output, "wb") as f:
            f.write(audio)
        print(f"\nWrote matching audio: {args.output}")
        print(f"Play it with: afplay {args.output}   (macOS)  |  ffplay {args.output}")


if __name__ == "__main__":
    main()
