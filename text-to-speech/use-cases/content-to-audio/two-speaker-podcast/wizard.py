"""Polly Podcasts — interactive episode generator.

Walks you through picking a model, a speaking style and two voices, then:
  1. Amazon Bedrock writes a short host/co-host script.
  2. Amazon Polly speaks each turn in the chosen voice.
  3. The segments are stitched into one MP3.

Requirements:
    - Python 3.10+
    - pip install -r requirements.txt
    - AWS credentials with access to Bedrock and Polly

Usage:
    python wizard.py
    python wizard.py --profile my-aws-profile
"""

import argparse
import sys
from pathlib import Path
from time import perf_counter

import boto3
from botocore.exceptions import ProfileNotFound
from simple_term_menu import TerminalMenu

import podcast_generation
import podcast_script
from config import (
    AWS_REGION,
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_NAME,
    GENERATIVE_ENGINE,
    MODELS,
    NEWSCASTER_ENGINE,
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def choose(options: list[str], title: str) -> int:
    """Show an arrow-key menu and return the chosen index."""
    index = TerminalMenu(options, title=title).show()
    if index is None:
        print("  Cancelled.")
        sys.exit(0)
    return index


def pick_model() -> tuple[str, str]:
    """Pick which Bedrock model writes the script. Returns (label, model_id)."""
    print("\n  Which model should write the script? (↑/↓, Enter)\n")
    labels = list(MODELS)
    options = [
        f"{label:<18}{MODELS[label]}{'   (default)' if label == DEFAULT_MODEL else ''}"
        for label in labels
    ]
    label = labels[choose(options, title="  Model:")]
    print(f"  → Model: {label} ({MODELS[label]})")
    return label, MODELS[label]


def pick_style() -> bool:
    """Pick the speaking style. Returns True for newscaster."""
    print("\n  Speaking style? (↑/↓, Enter)\n")
    index = choose(
        [
            "Conversational   generative engine, natural sounding, slower",
            "Newscaster       neural engine, newsreader tone, faster, 4 voices",
        ],
        title="  Style:",
    )
    newscaster = index == 1
    engine = NEWSCASTER_ENGINE if newscaster else GENERATIVE_ENGINE
    print(f"  → Style: {'Newscaster' if newscaster else 'Conversational'} ({engine} engine)")
    return newscaster


def pick_voice(role: str, voices: list[dict]) -> dict:
    """Pick a voice for one speaker."""
    print(f"\n  Voice for the {role}? (↑/↓, Enter)\n")
    options = [
        f"{v['name']:<12} {v['lang']:<7} {v['gender']:<7} {v['language']}" for v in voices
    ]
    voice = voices[choose(options, title=f"  {role.capitalize()}:")]
    print(f"  → {role.capitalize()}: {voice['name']} ({v_desc(voice)})")
    return voice


def v_desc(voice: dict) -> str:
    return f"{voice['lang']}, {voice['gender']}"


def prompt_topic() -> str | None:
    print()
    topic = input("  Episode topic (blank = let the model choose): ").strip()
    return topic or None


def prompt_output_name() -> Path:
    """Ask for a name and turn it into an .mp3 path.

    Output is always MP3, so the extension isn't worth asking about.
    """
    print()
    raw = input(f"  Output name [{DEFAULT_OUTPUT_NAME}]: ").strip()
    name = raw or DEFAULT_OUTPUT_NAME
    return Path(name).with_suffix(".mp3")


def confirm() -> None:
    answer = input("  Generate? [Y/n]: ").strip().lower()
    if answer and answer not in ("y", "yes"):
        print("  Aborted.")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a two-speaker podcast episode.")
    parser.add_argument(
        "-p",
        "--profile",
        default=None,
        help="AWS profile name (default: the standard credential chain)",
    )
    args = parser.parse_args()

    print()
    print("=" * 62)
    print("  Polly Podcasts")
    print("=" * 62)

    # Credentials first: better to fail now than after four questions.
    try:
        session = boto3.Session(profile_name=args.profile)
    except ProfileNotFound as e:
        sys.exit(f"\n  ERROR: {e}\n  Check ~/.aws/config, or omit --profile.")

    # --- Choices ---------------------------------------------------------
    # Topic, model, style, voices, filename. Voices have to come after the
    # style, because the style decides which voices are even offered.
    topic = prompt_topic()
    model_label, model_id = pick_model()
    newscaster = pick_style()

    print("\n  Fetching voices from Polly...", end=" ", flush=True)
    try:
        voices = podcast_generation.list_voices(session, newscaster)
    except Exception as e:
        sys.exit(f"FAILED\n\n  ERROR: {type(e).__name__}: {e}")
    print(f"{len(voices)} available")

    host = pick_voice("host", voices)
    cohost = pick_voice("co-host", voices)
    output_file = prompt_output_name()

    # --- Summary ---------------------------------------------------------
    print()
    print("-" * 62)
    print(f"  Model:    {model_label}")
    print(f"  Style:    {'Newscaster' if newscaster else 'Conversational'}")
    print(f"  Host:     {host['name']} ({v_desc(host)})")
    print(f"  Co-host:  {cohost['name']} ({v_desc(cohost)})")
    print(f"  Topic:    {topic or '(model will choose)'}")
    print(f"  Output:   {output_file}")
    print(f"  Region:   {AWS_REGION}")
    print("-" * 62)
    print()
    confirm()
    print()

    # --- 1. Script -------------------------------------------------------
    print(f"[1/3] Writing the script with {model_label}...", end=" ", flush=True)
    try:
        script, bedrock_usage = podcast_script.generate(
            session, model_id, host["name"], cohost["name"], topic
        )
    except Exception as e:
        sys.exit(f"FAILED\n\n  ERROR: {type(e).__name__}: {e}")
    print(f"OK ({len(script)} turns)")

    for i, turn in enumerate(script, 1):
        text = turn["text"]
        preview = text[:76] + ("..." if len(text) > 76 else "")
        print(f"      {i}. [{turn['speaker']}] {preview}")

    # --- 2. Audio --------------------------------------------------------
    print("[2/3] Synthesizing with Polly...")
    started = perf_counter()
    try:
        audio, polly_characters = podcast_generation.synthesize(
            session,
            script,
            {"host": host["id"], "cohost": cohost["id"]},
            newscaster,
            on_turn=lambda i, total, speaker, vid, size, secs: print(
                f"      Turn {i}/{total} — {speaker} ({vid}): {size:,} bytes, {secs:.1f}s"
            ),
        )
    except Exception as e:
        sys.exit(f"\n  ERROR: {type(e).__name__}: {e}")
    elapsed = perf_counter() - started

    # --- 3. Save ---------------------------------------------------------
    print("[3/3] Saving...", end=" ", flush=True)
    output_file.write_bytes(audio)
    print("OK")

    print()
    print("=" * 62)
    print("  Done")
    print("=" * 62)
    print(f"  File:  {output_file}  ({len(audio):,} bytes)")
    print(f"  Time:  {elapsed:.1f}s of synthesis")
    print()
    print("  Usage")
    print(
        "  Bedrock: "
        f"{bedrock_usage['inputTokens']:,} input + "
        f"{bedrock_usage['outputTokens']:,} output = "
        f"{bedrock_usage['totalTokens']:,} total tokens"
    )
    print(f"  Polly:   {polly_characters:,} billable characters")
    print(f"\n  Play it:  afplay {output_file}")
    print()


if __name__ == "__main__":
    main()
