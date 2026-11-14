"""Describe Voices — Amazon Polly DescribeVoices.

Discover which voices exist, and which engines and languages each supports,
before you synthesize. DescribeVoices is paginated; this example follows
NextToken to fetch every page and prints a table.

    - Filter by --engine   (standard | neural | long-form | generative)
    - Filter by --language-code (e.g. en-US)
    - --include-additional-languages surfaces bilingual voices

See https://docs.aws.amazon.com/polly/latest/dg/API_DescribeVoices.html

Requirements:
    - Python 3.10+
    - boto3
    - AWS credentials configured (named profile or environment variables)
    - IAM permission: polly:DescribeVoices

Usage:
    python describe_voices.py --engine generative --region us-east-1
    python describe_voices.py --engine generative --language-code en-US \
        --region us-east-1
    python describe_voices.py --engine generative --language-code hi-IN \
        --include-additional-languages --region us-east-1
    python describe_voices.py --profile my-aws-profile --region us-west-2
"""

import argparse
import sys


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def parse_args():
    parser = argparse.ArgumentParser(description="Describe Amazon Polly voices.")
    parser.add_argument(
        "--engine",
        default="generative",
        choices=("standard", "neural", "long-form", "generative"),
        help="Only voices that support this engine (default: generative).",
    )
    parser.add_argument("--language-code", default=None, help="Filter by language, e.g. en-US.")
    parser.add_argument(
        "--include-additional-languages",
        action="store_true",
        help="Include bilingual voices that support extra languages.",
    )
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    return parser.parse_args()


def describe_all_voices(client, engine, language_code, include_additional):
    """Return every voice, following NextToken across pages."""
    voices = []
    params = {"IncludeAdditionalLanguageCodes": include_additional}
    if engine:
        params["Engine"] = engine
    if language_code:
        params["LanguageCode"] = language_code

    while True:
        response = client.describe_voices(**params)
        voices.extend(response.get("Voices", []))
        token = response.get("NextToken")
        if not token:
            break
        params["NextToken"] = token
    return voices


def main():
    args = parse_args()

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    try:
        client = make_client(args.profile, args.region)
        print("DescribeVoices request:")
        print(f"  Region:                       {client.meta.region_name}")
        print(f"  Engine:                       {args.engine}")
        print(f"  Language code:                {args.language_code or 'all'}")
        print(
            "  Include additional languages: "
            f"{'yes' if args.include_additional_languages else 'no'}"
        )
        print()
        voices = describe_all_voices(
            client, args.engine, args.language_code, args.include_additional_languages
        )
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: DescribeVoices failed: {e}")
        sys.exit(1)

    voices.sort(key=lambda v: (v.get("LanguageCode", ""), v.get("Id", "")))

    if args.include_additional_languages:
        print(f"{'Id':<14}{'Language':<10}{'Gender':<8}{'Additional languages'}")
    else:
        print(f"{'Id':<14}{'Language':<10}{'Gender'}")
    print("-" * 70)
    for v in voices:
        if args.include_additional_languages:
            additional = ", ".join(v.get("AdditionalLanguageCodes", [])) or "-"
            row = (
                f"{v.get('Id',''):<14}"
                f"{v.get('LanguageCode',''):<10}"
                f"{v.get('Gender',''):<8}"
                f"{additional}"
            )
        else:
            row = (
                f"{v.get('Id',''):<14}"
                f"{v.get('LanguageCode',''):<10}"
                f"{v.get('Gender','')}"
            )
        print(row)
    print("-" * 70)
    print(f"{len(voices)} matching voice(s).")


if __name__ == "__main__":
    main()
