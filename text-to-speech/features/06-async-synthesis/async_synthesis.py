"""Async Synthesis — Amazon Polly StartSpeechSynthesisTask.

For input beyond the 6,000-character SynthesizeSpeech limit, use asynchronous
tasks. Polly synthesizes in the background and writes the result to an S3
bucket you own. You poll for completion and can download the generated audio.

Subcommands:
    start   Start a task from text or a file; optionally poll until done
    get     Look up one task by its TaskId
    list    List recent tasks, optionally filtered by status

See https://docs.aws.amazon.com/polly/latest/dg/asynchronous.html

Requirements:
    - Python 3.10+
    - boto3
    - An S3 bucket you own, in the same region
    - AWS credentials configured (named profile or environment variables)
    - IAM: polly:StartSpeechSynthesisTask,
      polly:GetSpeechSynthesisTask, polly:ListSpeechSynthesisTasks,
      s3:PutObject on the output bucket, and s3:GetObject when downloading

Usage:
    python async_synthesis.py start --bucket my-bucket-polly-outputs \
        --text-file sample-long-text.txt --wait \
        --download-to async-synthesis.mp3
    python async_synthesis.py start --bucket my-bucket-polly-outputs \
        --text "A short asynchronous request."
    python async_synthesis.py get --task-id <id>
    python async_synthesis.py list --status completed
"""

import argparse
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

AUDIO_FORMATS = ("mp3", "ogg_vorbis", "pcm")
MAX_TOTAL_CHARACTERS = 200_000


class TaskFailedError(RuntimeError):
    pass


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def make_s3_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("s3", region_name=region)


def parse_args():
    parser = argparse.ArgumentParser(description="Amazon Polly asynchronous synthesis tasks.")
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a synthesis task.")
    p_start.add_argument("--bucket", required=True, help="Output S3 bucket (must be in --region).")
    p_start.add_argument(
        "--key-prefix",
        default=None,
        help="S3 key prefix (default: a unique polly/async-synthesis-* prefix).",
    )
    src = p_start.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Inline text to synthesize.")
    src.add_argument("--text-file", help="Path to a UTF-8 text file to synthesize.")
    p_start.add_argument("--voice", default="Tiffany", help="Voice ID (default: Tiffany).")
    p_start.add_argument(
        "--engine",
        default="generative",
        choices=("standard", "neural", "long-form", "generative"),
        help="Engine (default: generative).",
    )
    p_start.add_argument(
        "--format",
        dest="output_format",
        default="mp3",
        choices=AUDIO_FORMATS,
        help="Output format (default: mp3).",
    )
    p_start.add_argument("--text-type", default="text", choices=("text", "ssml"), help="text or ssml.")
    p_start.add_argument("--wait", action="store_true", help="Poll until the task finishes.")
    p_start.add_argument(
        "--download-to",
        default=None,
        metavar="PATH",
        help="Download completed audio locally; requires --wait.",
    )
    p_start.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Maximum seconds to wait with --wait (default: 300).",
    )

    p_get = sub.add_parser("get", help="Get one task by id.")
    p_get.add_argument("--task-id", required=True)

    p_list = sub.add_parser("list", help="List recent tasks.")
    p_list.add_argument(
        "--status",
        choices=("scheduled", "inProgress", "completed", "failed"),
        default=None,
    )
    p_list.add_argument("--max", type=int, default=20, help="Max tasks to show (default: 20).")

    return parser.parse_args()


def print_task(task):
    print(f"  TaskId:      {task.get('TaskId')}")
    status = f"  Status:      {task.get('TaskStatus')}"
    if task.get("TaskStatusReason"):
        status += f"  {task['TaskStatusReason']}"
    print(status)
    print(f"  Voice:       {task.get('VoiceId')}  engine={task.get('Engine')}")
    print(f"  Characters:  {task.get('RequestCharacters')}")
    if task.get("OutputUri"):
        print(f"  OutputUri:   {task['OutputUri']}")


def parse_s3_output_uri(output_uri, expected_bucket=None):
    """Return (bucket, key) for Polly's S3 or HTTPS output URI."""
    parsed = urlparse(output_uri)
    path = unquote(parsed.path.lstrip("/"))

    if parsed.scheme == "s3":
        if not parsed.netloc or not path:
            raise ValueError(f"Could not parse S3 output URI: {output_uri}")
        return parsed.netloc, path

    if parsed.scheme in ("http", "https"):
        host = parsed.netloc.split(":", 1)[0]
        if host.startswith("s3.") or host == "s3.amazonaws.com":
            bucket, separator, key = path.partition("/")
            if separator and bucket and key:
                return bucket, key
        if ".s3." in host or host.endswith(".s3.amazonaws.com"):
            bucket = host.split(".s3", 1)[0]
            if bucket and path:
                return bucket, path
        if expected_bucket:
            prefix = expected_bucket + "/"
            key = path[len(prefix):] if path.startswith(prefix) else path
            if key:
                return expected_bucket, key

    raise ValueError(f"Could not parse Polly OutputUri: {output_uri}")


def print_output_location(task, expected_bucket):
    output_uri = task.get("OutputUri")
    if not output_uri:
        return None
    bucket, key = parse_s3_output_uri(output_uri, expected_bucket)
    s3_uri = f"s3://{bucket}/{key}"
    print(f"  S3Uri:       {s3_uri}")
    print(f"\nClean up the S3 object with:\n  aws s3 rm '{s3_uri}'")
    return bucket, key


def download_output(s3_client, bucket, key, local_path):
    destination = Path(local_path)
    if destination.parent != Path("."):
        destination.parent.mkdir(parents=True, exist_ok=True)
    s3_client.download_file(bucket, key, str(destination))
    print(f"\nDownloaded audio to {destination}")
    if destination.suffix.lower() == ".mp3":
        print(f"Play it with: afplay {destination}   (macOS)  |  ffplay {destination}")


def cmd_start(client, args, s3_client=None):
    if args.wait and args.timeout < 1:
        raise ValueError("--timeout must be at least 1 second.")
    if args.download_to and not args.wait:
        raise ValueError("--download-to requires --wait.")

    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text
    if not text or not text.strip():
        raise ValueError("Input text must not be empty.")
    if len(text) > MAX_TOTAL_CHARACTERS:
        raise ValueError(
            f"Input has {len(text):,} characters; the maximum is "
            f"{MAX_TOTAL_CHARACTERS:,}."
        )

    key_prefix = args.key_prefix or f"polly/async-synthesis-{uuid.uuid4().hex[:12]}"
    print(f"Using S3 key prefix: {key_prefix}")

    kwargs = {
        "Text": text,
        "TextType": args.text_type,
        "VoiceId": args.voice,
        "Engine": args.engine,
        "OutputFormat": args.output_format,
        "OutputS3BucketName": args.bucket,
        "OutputS3KeyPrefix": key_prefix,
    }
    task = client.start_speech_synthesis_task(**kwargs)["SynthesisTask"]
    print(f"Started task ({len(text)} characters):")
    print_task(task)

    if not args.wait:
        print("\nPoll it with: python async_synthesis.py get --task-id " + task["TaskId"])
        print_output_location(task, args.bucket)
        return

    task_id = task["TaskId"]
    print("\nPolling until complete...")
    deadline = time.monotonic() + args.timeout
    while True:
        task = client.get_speech_synthesis_task(TaskId=task_id)["SynthesisTask"]
        print(f"  status: {task['TaskStatus']}")
        if task["TaskStatus"] in ("completed", "failed"):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Task {task_id} did not finish within {args.timeout} seconds."
            )
        time.sleep(5)
    print()
    print_task(task)
    if task["TaskStatus"] == "failed":
        reason = task.get("TaskStatusReason", "No failure reason was returned.")
        raise TaskFailedError(f"Task {task_id} failed: {reason}")

    location = print_output_location(task, args.bucket)
    if args.download_to:
        if location is None:
            raise ValueError("The completed task did not return an OutputUri.")
        if s3_client is None:
            raise ValueError("An S3 client is required to download the output.")
        download_output(s3_client, *location, args.download_to)


def cmd_get(client, args):
    task = client.get_speech_synthesis_task(TaskId=args.task_id)["SynthesisTask"]
    print_task(task)
    if task["TaskStatus"] == "failed":
        reason = task.get("TaskStatusReason", "No failure reason was returned.")
        raise TaskFailedError(f"Task {args.task_id} failed: {reason}")
    print_output_location(task, None)


def cmd_list(client, args):
    if args.max < 1:
        raise ValueError("--max must be at least 1.")

    tasks = []
    token = None
    while len(tasks) < args.max:
        params = {"MaxResults": min(args.max - len(tasks), 100)}
        if args.status:
            params["Status"] = args.status
        if token:
            params["NextToken"] = token
        response = client.list_speech_synthesis_tasks(**params)
        tasks.extend(response.get("SynthesisTasks", []))
        token = response.get("NextToken")
        if not token:
            break
    if not tasks:
        print("No matching tasks.")
        return
    for t in tasks:
        print(f"  {t['TaskId']}  {t['TaskStatus']:<11}{t.get('VoiceId',''):<12}{t.get('CreationTime','')}")
    print(f"{len(tasks)} task(s).")


COMMANDS = {"get": cmd_get, "list": cmd_list}


def main():
    args = parse_args()

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    try:
        client = make_client(args.profile, args.region)
        if args.command == "start":
            s3_client = None
            if args.download_to and args.wait:
                s3_client = make_s3_client(args.profile, client.meta.region_name)
            cmd_start(client, args, s3_client)
        else:
            COMMANDS[args.command](client, args)
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: {args.command} failed: {e}")
        sys.exit(1)
    except (OSError, UnicodeError, TimeoutError, TaskFailedError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
