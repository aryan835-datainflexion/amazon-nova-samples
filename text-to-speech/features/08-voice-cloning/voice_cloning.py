"""Voice Cloning — create and use an Amazon Polly cloned voice.

The primary example is the ``create`` command: create a generative voice from
pre-recorded S3 objects for one consenting speaker, then wait for the voice to
become active. Supporting commands synthesize speech, start long-form
synthesis, inspect the voice, and delete it.

CreateVoice also accepts audio bytes directly. This CLI uses S3 references to
keep the main workflow easy to run with multiple recordings.

Subcommands:
    create       Create a cloned voice from 1-10 pre-recorded S3 objects
    get          Get a cloned voice and its creation status
    synthesize   Generate an audio file synchronously with an active voice
    start        Start a long-form synthesis task that writes audio to S3
    delete       Permanently delete a cloned voice

Requirements:
    - Python 3.10+
    - The GA boto3 service model for Amazon Polly voice cloning
    - For this CLI, recordings in S3 in the same Region as the cloned voice
    - The speaker's consent and acceptance of the applicable AWS terms
    - AWS credentials configured through the default credential chain

Usage:
    python voice_cloning.py create --name MyClonedVoice \
        --language-code en-US \
        --recording s3://my-bucket-polly-outputs/take1.wav \
        --consent-reference speaker-0042 --accept-terms
    python voice_cloning.py get --voice-id vc-0123456789
    python voice_cloning.py synthesize --voice-id vc-0123456789
    python voice_cloning.py start --voice-id vc-0123456789 \
        --bucket my-bucket-polly-outputs --text-file chapter-01.txt
    python voice_cloning.py delete --voice-id vc-0123456789
"""

import argparse
import re
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

VOICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
S3_URI_PATTERN = re.compile(r"^s3://[^/]+/.+")
TERMINAL_VOICE_STATUSES = ("active", "failed")
DEFAULT_TEXT = "Hello! This is my very own Amazon Polly voice."
FORMAT_EXTENSIONS = {"mp3": "mp3", "ogg_vorbis": "ogg", "pcm": "pcm"}


class VoiceCreationFailedError(RuntimeError):
    pass


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


# ---------------------------------------------------------------------------
# Primary example: create a cloned voice
# ---------------------------------------------------------------------------


def print_voice(voice):
    print(f"  VoiceId:      {voice.get('Id')}")
    print(f"  Name:         {voice.get('Name')}")
    print(f"  Status:       {voice.get('Status')}")
    print(f"  Language:     {voice.get('LanguageCode')}")
    if voice.get("Arn"):
        print(f"  ARN:          {voice['Arn']}")
    if voice.get("StatusReason"):
        print(f"  StatusReason: {voice['StatusReason']}")


def wait_for_voice(client, voice, timeout, poll_interval):
    voice_id = voice["Id"]
    deadline = time.monotonic() + timeout

    while voice.get("Status") not in TERMINAL_VOICE_STATUSES:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{voice_id} is still {voice.get('Status', 'being created')} "
                f"after {timeout} seconds."
            )
        print(
            f"Voice {voice_id} is {voice.get('Status', 'being created')}; "
            f"checking again in {poll_interval}s..."
        )
        time.sleep(poll_interval)
        voice = client.get_voice(VoiceId=voice_id)["Voice"]

    print_voice(voice)
    if voice["Status"] == "failed":
        reason = voice.get("StatusReason", "creation failed")
        raise VoiceCreationFailedError(f"{voice_id}: {reason}")
    return voice


def create_voice(client, args):
    """CreateVoice request and optional wait for the voice to become active."""
    if not args.accept_terms:
        raise ValueError(
            "--accept-terms is required. Obtain the speaker's consent and review "
            "the applicable AWS terms before creating a voice."
        )
    if not 1 <= len(args.recording) <= 10:
        raise ValueError("Provide between 1 and 10 --recording values.")

    request = {
        "Name": args.name,
        "LanguageCode": args.language_code,
        "TermsAccepted": True,
        "VoiceCreationData": {
            "Recordings": [
                {"Format": args.format, "Data": {"S3Url": uri}}
                for uri in args.recording
            ]
        },
        "Tags": {"consent-record": args.consent_reference},
    }
    if args.kms_key_arn:
        request["CustomerManagedEncryption"] = {"KmsKeyArn": args.kms_key_arn}

    voice = client.create_voice(**request)["Voice"]
    print("Voice creation started:")
    print_voice(voice)
    print(
        "\nStore this voice ID with its Region, language, owner, and consent record."
    )
    if not args.no_wait:
        print("\nWaiting for the voice to become active (typically 5-10 minutes)...")
        wait_for_voice(client, voice, args.timeout, args.poll_interval)


# ---------------------------------------------------------------------------
# Supporting lifecycle operations
# ---------------------------------------------------------------------------


def get_voice(client, args):
    voice = client.get_voice(VoiceId=args.voice_id)["Voice"]
    print_voice(voice)


def synthesize_speech(client, args):
    output = args.output or f"my-voice.{FORMAT_EXTENSIONS[args.output_format]}"
    request = {
        "VoiceId": args.voice_id,
        "Engine": "generative",
        "OutputFormat": args.output_format,
        "Text": args.text,
    }
    if args.language_code:
        request["LanguageCode"] = args.language_code

    response = client.synthesize_speech(**request)
    with closing(response["AudioStream"]) as stream:
        audio = stream.read()
    Path(output).write_bytes(audio)

    billed = response.get("RequestCharacters", "?")
    print(f"Wrote {output} (billed characters: {billed}).")
    if args.output_format == "mp3":
        print(f"Play it with: afplay {output}   (macOS)  |  ffplay {output}")


def start_long_form_synthesis(client, args):
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text
    if not text or not text.strip():
        raise ValueError("Input text must not be empty.")

    key_prefix = (
        args.key_prefix or f"narration/voice-cloning-{uuid.uuid4().hex[:12]}"
    )
    request = {
        "VoiceId": args.voice_id,
        "Engine": "generative",
        "OutputFormat": args.output_format,
        "OutputS3BucketName": args.bucket,
        "OutputS3KeyPrefix": key_prefix,
        "Text": text,
    }
    if args.language_code:
        request["LanguageCode"] = args.language_code
    if args.sns_topic_arn:
        request["SnsTopicArn"] = args.sns_topic_arn

    task = client.start_speech_synthesis_task(**request)["SynthesisTask"]
    print("Started long-form synthesis:")
    print(f"  TaskId:    {task.get('TaskId')}")
    print(f"  Status:    {task.get('TaskStatus')}")
    print(f"  OutputUri: {task.get('OutputUri')}")
    print(
        "\nPoll with GetSpeechSynthesisTask until the status is completed or failed."
    )


def delete_voice(client, args):
    client.delete_voice(VoiceId=args.voice_id)
    print(f"Deleted cloned voice {args.voice_id} from {client.meta.region_name}.")


# ---------------------------------------------------------------------------
# CLI arguments and dispatch
# ---------------------------------------------------------------------------


def voice_name(value):
    if not VOICE_NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must contain 1-64 letters, digits, hyphens, or underscores"
        )
    return value


def s3_uri(value):
    if not S3_URI_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must be an S3 object URI such as s3://bucket/path/take.wav"
        )
    return value


def positive_timeout(value):
    timeout = int(value)
    if timeout < 1:
        raise argparse.ArgumentTypeError("must be at least 1 second")
    return timeout


def add_aws_options(parser):
    """Allow AWS options after a subcommand without overwriting global values."""
    parser.add_argument(
        "-p",
        "--profile",
        default=argparse.SUPPRESS,
        help="AWS profile name.",
    )
    parser.add_argument(
        "-r",
        "--region",
        default=argparse.SUPPRESS,
        help="AWS Region override (default: configured Region).",
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create, use, inspect, and delete Amazon Polly cloned voices."
    )
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a cloned voice.")
    p_create.add_argument("--name", required=True, type=voice_name)
    p_create.add_argument(
        "--language-code",
        required=True,
        help="Language spoken in every recording, for example en-US.",
    )
    p_create.add_argument(
        "--recording",
        required=True,
        action="append",
        type=s3_uri,
        metavar="S3_URI",
        help=(
            "Pre-recorded S3 object URI; repeat for 1-10 takes. "
            "CreateVoice also supports direct audio bytes, but this CLI uses S3."
        ),
    )
    p_create.add_argument(
        "--format",
        choices=("wav", "flac", "ogg_vorbis", "mp3"),
        default="wav",
        help="Recording format sent for every take (default: wav).",
    )
    p_create.add_argument(
        "--consent-reference",
        required=True,
        help="Your internal speaker-consent reference, stored as a voice tag.",
    )
    p_create.add_argument(
        "--accept-terms",
        action="store_true",
        help="Confirm speaker consent and acceptance of the applicable AWS terms.",
    )
    p_create.add_argument(
        "--kms-key-arn",
        default=None,
        help="Optional same-Region symmetric customer-managed KMS key ARN.",
    )
    p_create.add_argument(
        "--no-wait",
        action="store_true",
        help="Return after creation starts instead of polling until active or failed.",
    )
    p_create.add_argument(
        "--timeout",
        type=positive_timeout,
        default=1200,
        help="Maximum seconds to wait (default: 1200).",
    )
    p_create.add_argument(
        "--poll-interval",
        type=positive_timeout,
        default=30,
        help="Seconds between GetVoice calls (default: 30).",
    )

    p_get = sub.add_parser("get", help="Get a voice and its creation status.")
    p_get.add_argument("--voice-id", required=True)

    p_synth = sub.add_parser(
        "synthesize", help="Synchronously synthesize speech with an active cloned voice."
    )
    p_synth.add_argument("--voice-id", required=True)
    p_synth.add_argument("--language-code", default=None)
    p_synth.add_argument("--text", default=DEFAULT_TEXT)
    p_synth.add_argument(
        "--format",
        dest="output_format",
        choices=("mp3", "ogg_vorbis", "pcm"),
        default="mp3",
    )
    p_synth.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (default: my-voice.<format extension>).",
    )

    p_start = sub.add_parser(
        "start", help="Start a long-form synthesis task that writes audio to S3."
    )
    p_start.add_argument("--voice-id", required=True)
    p_start.add_argument("--language-code", default=None)
    p_start.add_argument("--bucket", required=True, help="Output S3 bucket name.")
    p_start.add_argument(
        "--key-prefix",
        default=None,
        help="Output key prefix (default: unique narration/voice-cloning-* value).",
    )
    text_source = p_start.add_mutually_exclusive_group(required=True)
    text_source.add_argument("--text", help="Inline text to synthesize.")
    text_source.add_argument("--text-file", help="UTF-8 text file to synthesize.")
    p_start.add_argument(
        "--format",
        dest="output_format",
        choices=("mp3", "ogg_vorbis", "pcm"),
        default="mp3",
    )
    p_start.add_argument(
        "--sns-topic-arn",
        default=None,
        help="Optional SNS topic for task status notifications.",
    )

    p_delete = sub.add_parser("delete", help="Permanently delete a cloned voice.")
    p_delete.add_argument("--voice-id", required=True)

    for command_parser in (p_create, p_get, p_synth, p_start, p_delete):
        add_aws_options(command_parser)

    return parser.parse_args()


COMMANDS = {
    "create": create_voice,
    "get": get_voice,
    "synthesize": synthesize_speech,
    "start": start_long_form_synthesis,
    "delete": delete_voice,
}


def main():
    args = parse_args()

    try:
        from botocore.exceptions import (
            BotoCoreError,
            ClientError,
            NoCredentialsError,
            ParamValidationError,
        )
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    try:
        client = make_client(args.profile, args.region)
        if not hasattr(client, "create_voice"):
            raise RuntimeError(
                "This boto3 service model does not include the GA voice-cloning "
                "API. Upgrade to the GA SDK release and try again."
            )
        COMMANDS[args.command](client, args)
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except ParamValidationError as error:
        print(f"ERROR: Invalid parameters for {args.command}: {error}")
        sys.exit(1)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "ClientError")
        message = error.response.get("Error", {}).get("Message", str(error))
        print(f"ERROR: {args.command} failed ({code}): {message}")
        sys.exit(1)
    except (BotoCoreError, OSError, UnicodeError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
