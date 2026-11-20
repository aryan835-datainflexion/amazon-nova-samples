#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from live_translator.config import AppConfig, load_config  # noqa: E402
from live_translator.pipeline import LiveTranslationPipeline  # noqa: E402

VALID_MODES = {"si", "half-duplex"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phrase-level live speech translator: Transcribe -> Translate -> Polly."
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--region", default=os.getenv("AWS_REGION"))
    parser.add_argument("--source", help="Transcribe source locale, for example ja-JP, or auto.")
    parser.add_argument("--target", help="Amazon Translate target language, for example en.")
    parser.add_argument(
        "--voice",
        help="Amazon Polly voice ID, for example Tiffany or Matthew.",
    )
    parser.add_argument(
        "--voice-language",
        help="Amazon Polly language code matching the target, for example en-US or es-US.",
    )
    parser.add_argument(
        "--input-device",
        type=_audio_device,
        help="Microphone device index or name. Use --list-devices to discover devices.",
    )
    parser.add_argument(
        "--output-device",
        type=_audio_device,
        help="Speaker device index or name. Use --list-devices to discover devices.",
    )
    parser.add_argument(
        "--engine",
        help="Amazon Polly engine, for example generative, neural, or standard.",
    )
    parser.add_argument(
        "--mode",
        choices=["si", "half-duplex"],
        help="si keeps the mic live during playback; half-duplex sends silence while Polly plays.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate local imports, config, and AWS credential resolution without streaming audio.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices and exit.",
    )
    return parser.parse_args()


def _audio_device(value: str) -> int | str:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("audio device cannot be empty")
    try:
        return int(value)
    except ValueError:
        return value


def apply_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    aws = config.aws
    audio = config.audio
    translator = config.translator
    polly = config.polly

    if args.region:
        aws = replace(aws, region=args.region)
    if args.input_device is not None:
        audio = replace(audio, input_device=args.input_device)
    if args.output_device is not None:
        audio = replace(audio, output_device=args.output_device)
    if args.source:
        translator = replace(translator, source_language=args.source)
    if args.target:
        translator = replace(translator, target_language=args.target)
    if args.mode:
        translator = replace(translator, mode=args.mode)
    if args.voice:
        polly = replace(polly, voice_id=args.voice)
    if args.voice_language:
        polly = replace(polly, language_code=args.voice_language)
    if args.engine:
        polly = replace(polly, engine=args.engine)

    return AppConfig(aws=aws, audio=audio, translator=translator, polly=polly)


def validate_config(config: AppConfig) -> None:
    if config.translator.mode not in VALID_MODES:
        raise ValueError("translator.mode must be one of: si, half-duplex")

    if config.audio.sample_rate != 16000:
        raise ValueError("audio.sample_rate must be 16000 for this PCM sample")

    if config.audio.channels != 1:
        raise ValueError("audio.channels must be 1 for this mono PCM sample")

    if config.audio.dtype != "int16":
        raise ValueError("audio.dtype must be int16 for Transcribe and Polly PCM")

    if config.polly.output_format != "pcm":
        raise ValueError("polly.output_format must be pcm for direct RawOutputStream playback")

    if config.audio.mic_block_frames <= 0:
        raise ValueError("audio.mic_block_frames must be greater than zero")

    if config.audio.playback_chunk_bytes <= 0:
        raise ValueError("audio.playback_chunk_bytes must be greater than zero")

    for field_name, device in (
        ("audio.input_device", config.audio.input_device),
        ("audio.output_device", config.audio.output_device),
    ):
        if isinstance(device, int) and device < 0:
            raise ValueError(f"{field_name} must be a non-negative device index")
        if isinstance(device, str) and not device.strip():
            raise ValueError(f"{field_name} cannot be empty")

    if config.translator.queue_size <= 0:
        raise ValueError("translator.queue_size must be greater than zero")

    target_family = _language_family(config.translator.target_language)
    voice_family = _language_family(config.polly.language_code)
    if target_family != voice_family:
        raise ValueError(
            "polly.language_code must match translator.target_language "
            f"(target={config.translator.target_language!r}, "
            f"voice language={config.polly.language_code!r}); "
            "update config.yaml or use --voice-language"
        )

    if config.translator.source_language == "auto":
        options = config.translator.auto_language_options
        if len(options) < 2:
            raise ValueError(
                "translator.auto_language_options must contain at least two locales "
                "when source_language is auto"
            )

        primary_languages = [_primary_language(option) for option in options]
        duplicates = sorted(
            {
                language
                for language in primary_languages
                if primary_languages.count(language) > 1
            }
        )
        if duplicates:
            raise ValueError(
                "Transcribe language identification supports one locale per language; "
                f"remove duplicate language families: {', '.join(duplicates)}"
            )


def _primary_language(locale: str) -> str:
    return locale.split("-")[0].lower()


def _language_family(code: str) -> str:
    family = _primary_language(code)
    return {
        "arb": "ar",
        "cmn": "zh",
        "yue": "zh",
    }.get(family, family)


def preflight(config: AppConfig) -> None:
    validate_config(config)
    from live_translator.audio import check_audio_devices

    input_device, output_device = check_audio_devices(config.audio)
    session = boto3.Session(region_name=config.aws.region)
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS credentials found in the default credential chain.")

    _check_polly_voice(session, config)
    _check_translate_text(session, config)

    print("Preflight OK")
    print(f"  Region  : {config.aws.region}")
    print(f"  Source  : {config.translator.source_language}")
    print(f"  Target  : {config.translator.target_language}")
    print(
        f"  Voice   : {config.polly.voice_id} "
        f"({config.polly.engine}, {config.polly.language_code})"
    )
    print(f"  Input   : {input_device}")
    print(f"  Output  : {output_device}")
    print("  Creds   : resolved from the standard AWS credential chain")
    print("  Polly   : configured voice supports the selected engine/language")
    print("  Translate: tiny TranslateText probe succeeded")
    print("  Transcribe: request configuration is valid; live stream starts at runtime")


def _check_polly_voice(session: boto3.Session, config: AppConfig) -> None:
    client = session.client("polly", region_name=config.aws.region)
    kwargs = {
        "Engine": config.polly.engine,
        "LanguageCode": config.polly.language_code,
        "IncludeAdditionalLanguageCodes": True,
    }
    voices = []
    while True:
        response = client.describe_voices(**kwargs)
        voices.extend(response.get("Voices", []))
        next_token = response.get("NextToken")
        if not next_token:
            break
        kwargs["NextToken"] = next_token

    if not any(voice.get("Id") == config.polly.voice_id for voice in voices):
        raise RuntimeError(
            f"Polly voice {config.polly.voice_id!r} was not returned for "
            f"engine={config.polly.engine!r}, language={config.polly.language_code!r}. "
            "Choose compatible settings or override "
            "--voice/--voice-language/--engine."
        )


def _check_translate_text(session: boto3.Session, config: AppConfig) -> None:
    client = session.client("translate", region_name=config.aws.region)
    target = config.translator.target_language
    if target == "en":
        source = "es"
        text = "hola"
    else:
        source = "en"
        text = "hello"

    client.translate_text(
        Text=text,
        SourceLanguageCode=source,
        TargetLanguageCode=target,
    )


async def amain() -> None:
    args = parse_args()
    if args.list_devices:
        from live_translator.audio import format_audio_devices

        print(format_audio_devices())
        return

    config = apply_overrides(load_config(args.config), args)
    validate_config(config)
    if args.check:
        preflight(config)
        return

    print("=" * 72)
    print("Live Speech Translator")
    print("=" * 72)
    print("Pipeline : Amazon Transcribe -> Amazon Translate -> Amazon Polly")
    print(f"Source   : {config.translator.source_language}")
    print(f"Target   : {config.translator.target_language}")
    print(
        f"Voice    : {config.polly.voice_id} "
        f"({config.polly.engine}, {config.polly.language_code})"
    )
    input_device = (
        config.audio.input_device
        if config.audio.input_device is not None
        else "default"
    )
    output_device = (
        config.audio.output_device
        if config.audio.output_device is not None
        else "default"
    )
    print(f"Input    : {input_device}")
    print(f"Output   : {output_device}")
    print(f"Mode     : {config.translator.mode}")
    print("Tip      : use headphones in si mode to avoid speaker-to-mic feedback.")
    print("Stop     : Ctrl+C")
    print("-" * 72)

    await LiveTranslationPipeline(config).run()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:  # noqa: BLE001 - CLI sample should fail readably
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
