"""Lexicons — Amazon Polly PutLexicon / GetLexicon / ListLexicons / DeleteLexicon.

A pronunciation lexicon (PLS document) customizes how Polly says specific words:
expand acronyms, fix names, override pronunciation by phoneme. Lexicons are
stored per region and applied at synthesis time via LexiconNames.

Subcommands:
    put     Upload example.pls under a name
    get     Fetch a stored lexicon and print it
    list    List stored lexicons in the region
    delete  Delete a stored lexicon
    apply   Synthesize text with the lexicon applied (SynthesizeSpeech)

See https://docs.aws.amazon.com/polly/latest/dg/managing-lexicons.html

Requirements:
    - Python 3.10+
    - boto3
    - AWS credentials configured (named profile or environment variables)
    - IAM: polly:PutLexicon, polly:GetLexicon, polly:ListLexicons,
      polly:DeleteLexicon, and polly:SynthesizeSpeech

Usage:
    python lexicons.py put --name MyLexicon --file example.pls
    python lexicons.py list
    python lexicons.py get --name MyLexicon
    python lexicons.py apply --name MyLexicon --text "Try AWS with Polly."
    python lexicons.py delete --name MyLexicon
"""

import argparse
import re
import sys
from contextlib import closing

LEXICON_NAME_PATTERN = re.compile(r"^[0-9A-Za-z]{1,20}$")


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def lexicon_name(value):
    if not LEXICON_NAME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "must contain 1-20 alphanumeric characters"
        )
    return value


def parse_args():
    parser = argparse.ArgumentParser(description="Manage Amazon Polly lexicons.")
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_put = sub.add_parser("put", help="Upload a PLS lexicon.")
    p_put.add_argument(
        "--name",
        required=True,
        type=lexicon_name,
        help="Lexicon name (1-20 alphanumeric characters).",
    )
    p_put.add_argument("--file", default="example.pls", help="PLS file to upload (default: example.pls).")

    p_get = sub.add_parser("get", help="Fetch a lexicon.")
    p_get.add_argument("--name", required=True, type=lexicon_name)

    sub.add_parser("list", help="List lexicons.")

    p_del = sub.add_parser("delete", help="Delete a lexicon.")
    p_del.add_argument("--name", required=True, type=lexicon_name)

    p_apply = sub.add_parser("apply", help="Synthesize text with a lexicon applied.")
    p_apply.add_argument(
        "--name",
        required=True,
        type=lexicon_name,
        help="Lexicon name to apply.",
    )
    p_apply.add_argument("--text", default="Try AWS with Polly.", help="Text to synthesize.")
    p_apply.add_argument("--voice", default="Tiffany", help="Voice ID (default: Tiffany).")
    p_apply.add_argument(
        "--engine",
        default="generative",
        choices=("standard", "neural", "long-form", "generative"),
        help="Engine (default: generative).",
    )
    p_apply.add_argument(
        "-o",
        "--output",
        default="lexicon-applied.mp3",
        help="Output file (default: lexicon-applied.mp3).",
    )

    return parser.parse_args()


def cmd_put(client, args):
    with open(args.file, "r", encoding="utf-8") as f:
        content = f.read()
    client.put_lexicon(Name=args.name, Content=content)
    print(
        f"Stored lexicon '{args.name}' from {args.file} "
        f"in {client.meta.region_name}."
    )


def cmd_get(client, args):
    response = client.get_lexicon(Name=args.name)
    attrs = response.get("LexiconAttributes", {})
    print(f"Lexicon '{args.name}' in {client.meta.region_name}:")
    for key in ("Alphabet", "LanguageCode", "LexiconArn", "LexemesCount", "Size"):
        if key in attrs:
            print(f"  {key}: {attrs[key]}")
    print("\nContent:\n" + response["Lexicon"]["Content"])


def cmd_list(client, args):
    lexicons = []
    params = {}
    while True:
        response = client.list_lexicons(**params)
        lexicons.extend(response.get("Lexicons", []))
        token = response.get("NextToken")
        if not token:
            break
        params["NextToken"] = token

    if not lexicons:
        print(f"No lexicons stored in {client.meta.region_name}.")
        return
    for lex in lexicons:
        attrs = lex.get("Attributes", {})
        print(f"  {lex['Name']:<20} lang={attrs.get('LanguageCode','?'):<8} lexemes={attrs.get('LexemesCount','?')}")
    print(f"{len(lexicons)} lexicon(s) in {client.meta.region_name}.")


def cmd_delete(client, args):
    client.delete_lexicon(Name=args.name)
    print(f"Deleted lexicon '{args.name}' from {client.meta.region_name}.")


def cmd_apply(client, args):
    response = client.synthesize_speech(
        Text=args.text,
        VoiceId=args.voice,
        Engine=args.engine,
        OutputFormat="mp3",
        LexiconNames=[args.name],
    )
    with closing(response["AudioStream"]) as audio_stream:
        audio = audio_stream.read()
    with open(args.output, "wb") as f:
        f.write(audio)
    print(
        f"Wrote {args.output} with lexicon '{args.name}' applied "
        f"in {client.meta.region_name}."
    )
    print(f"Play it with: afplay {args.output}   (macOS)  |  ffplay {args.output}")


COMMANDS = {
    "put": cmd_put,
    "get": cmd_get,
    "list": cmd_list,
    "delete": cmd_delete,
    "apply": cmd_apply,
}


def main():
    args = parse_args()

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    try:
        client = make_client(args.profile, args.region)
        COMMANDS[args.command](client, args)
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if args.command == "apply" and error_code == "LexiconNotFoundException":
            print(f"ERROR: Lexicon '{args.name}' is not available yet.")
            print("PutLexicon is eventually consistent. Wait a few seconds and retry.")
        elif args.command == "put" and error_code == "InvalidLexiconException":
            print(f"ERROR: {args.file} is not a valid PLS lexicon: {e}")
        else:
            print(f"ERROR: {args.command} failed: {e}")
        sys.exit(1)
    except BotoCoreError as e:
        print(f"ERROR: {args.command} failed: {e}")
        sys.exit(1)
    except (OSError, UnicodeError) as e:
        print(f"ERROR: File operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
