"""Voice Control with SSML — Amazon Polly SynthesizeSpeech with TextType=ssml.

Speech Synthesis Markup Language (SSML) gives you fine control over how text is
spoken: pauses, emphasis, pitch and rate, spelling things out, pronunciation by
phoneme, and domain styles like newscaster.

This example ships a set of named SSML snippets. Pick one with --tag, supply
your own with --ssml / --ssml-file, or run --list to see them all.
See https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html

Requirements:
    - Python 3.10+
    - boto3
    - AWS credentials configured (named profile or environment variables)
    - IAM permission: polly:SynthesizeSpeech

Usage:
    python voice_control_ssml.py --list
    python voice_control_ssml.py --tag break
    python voice_control_ssml.py --tag prosody --voice Matthew
    python voice_control_ssml.py --tag emphasis --engine standard --voice Matthew
    python voice_control_ssml.py --tag phoneme --engine neural --voice Matthew
    python voice_control_ssml.py --tag newscaster --engine neural --voice Joanna
    python voice_control_ssml.py --ssml '<speak>Hi <break time="1s"/> there.</speak>'
    python voice_control_ssml.py --ssml-file my.ssml -o out.mp3
"""

import argparse
import sys
from contextlib import closing
from pathlib import Path

# Named SSML samples. Each is a complete <speak> document. Tag support varies by
# engine. The default examples use generative where supported; emphasis
# requires standard, while phoneme and the "news" domain use neural here.
SAMPLES = {
    "break": (
        "<speak>There is a pause "
        '<break time="1s"/> right there, and a shorter one '
        '<break strength="weak"/> here.</speak>'
    ),
    "prosody": (
        "<speak>"
        '<prosody rate="slow">This sentence is spoken slowly.</prosody> '
        '<prosody rate="fast" volume="loud">'
        "This sentence is spoken quickly and loudly."
        "</prosody>"
        "</speak>"
    ),
    "emphasis": (
        "<speak>I <emphasis level=\"strong\">really</emphasis> mean it "
        "<emphasis level=\"reduced\">this time</emphasis>.</speak>"
    ),
    "say-as": (
        "<speak>"
        'Call <say-as interpret-as="telephone">2025550176</say-as> on '
        '<say-as interpret-as="date" format="ymd">2026-08-25</say-as>. '
        'Spell it: <say-as interpret-as="spell-out">Polly</say-as>.'
        "</speak>"
    ),
    "phoneme": (
        "<speak>You say "
        '<phoneme alphabet="ipa" ph="pɪˈkɑːn">pecan</phoneme>, I say '
        '<phoneme alphabet="ipa" ph="ˈpiːkæn">pecan</phoneme>.</speak>'
    ),
    "newscaster": (
        '<speak><amazon:domain name="news">'
        "And now, the headlines. Amazon Polly turns text into lifelike speech."
        "</amazon:domain></speak>"
    ),
}


def make_client(profile, region):
    import boto3

    session = boto3.Session(profile_name=profile)
    return session.client("polly", region_name=region)


def parse_args():
    parser = argparse.ArgumentParser(description="Synthesize SSML with Amazon Polly.")
    parser.add_argument("--list", action="store_true", help="List the built-in SSML samples and exit.")
    parser.add_argument("--tag", choices=sorted(SAMPLES), help="Which built-in SSML sample to speak.")
    parser.add_argument("--ssml", default=None, help="Inline SSML document (overrides --tag).")
    parser.add_argument("--ssml-file", default=None, help="Path to a file containing an SSML document.")
    parser.add_argument("--voice", default="Tiffany", help="Voice ID (default: Tiffany).")
    parser.add_argument(
        "--engine",
        default="generative",
        choices=("standard", "neural", "long-form", "generative"),
        help="Polly engine (default: generative). Domain styles require neural.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output filename (default: ssml-<tag>.mp3 or ssml-custom.mp3).",
    )
    parser.add_argument("-p", "--profile", default=None, help="AWS profile name.")
    parser.add_argument(
        "-r",
        "--region",
        default=None,
        help="AWS Region override (default: configured Region).",
    )
    return parser.parse_args()


def resolve_ssml(args):
    if args.ssml:
        return args.ssml
    if args.ssml_file:
        with open(args.ssml_file, "r", encoding="utf-8") as f:
            return f.read()
    if args.tag:
        return SAMPLES[args.tag]
    return SAMPLES["break"]


def default_output_name(args):
    if args.tag:
        label = args.tag
    elif args.ssml_file:
        label = Path(args.ssml_file).stem
    elif args.ssml:
        label = "custom"
    else:
        label = "break"
    return f"ssml-{label}.mp3"


def main():
    args = parse_args()

    if args.list:
        print("Built-in SSML samples (use --tag NAME):\n")
        for name, ssml in SAMPLES.items():
            print(f"  {name}:\n    {ssml}\n")
        return

    try:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        print("ERROR: boto3 is not installed. Run: pip install -r ../requirements.txt")
        sys.exit(1)

    ssml = resolve_ssml(args)
    output = args.output or default_output_name(args)
    print(f"Synthesizing SSML with {args.voice} ({args.engine}):\n  {ssml}\n")

    try:
        client = make_client(args.profile, args.region)
        response = client.synthesize_speech(
            Text=ssml,
            TextType="ssml",
            VoiceId=args.voice,
            Engine=args.engine,
            OutputFormat="mp3",
        )
    except NoCredentialsError:
        print("ERROR: No AWS credentials found. Configure a profile or environment variables.")
        sys.exit(1)
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR: Polly request failed: {e}")
        if args.tag == "emphasis":
            print("Tip: the emphasis tag requires the standard engine.")
            print("Try: --tag emphasis --engine standard --voice Matthew")
        elif args.tag == "phoneme":
            print("Tip: run this phoneme example with the neural engine.")
            print("Try: --tag phoneme --engine neural --voice Matthew")
        elif args.tag == "newscaster":
            print("Tip: the newscaster domain requires a supported neural voice.")
            print("Try: --tag newscaster --engine neural --voice Joanna")
        elif args.tag == "prosody":
            print("Tip: generative prosody supports rate and volume, but not pitch.")
        sys.exit(1)

    with closing(response["AudioStream"]) as audio_stream:
        audio = audio_stream.read()
    with open(output, "wb") as f:
        f.write(audio)
    print(f"Wrote {output}  (billed characters: {response.get('RequestCharacters', '?')})")
    print(f"Play it with: afplay {output}")


if __name__ == "__main__":
    main()
