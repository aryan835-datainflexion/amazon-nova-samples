from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AwsConfig:
    region: str = "us-east-1"


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    input_device: int | str | None = None
    output_device: int | str | None = None
    mic_block_frames: int = 2048
    playback_chunk_bytes: int = 8192


@dataclass(frozen=True)
class TranslatorConfig:
    source_language: str = "auto"
    identify_multiple_languages: bool = True
    target_language: str = "en"
    mode: str = "si"
    queue_size: int = 8
    skip_translation_when_source_matches_target: bool = True
    auto_language_options: list[str] = field(
        default_factory=lambda: [
            "en-US",
            "es-US",
            "fr-FR",
            "de-DE",
            "it-IT",
            "pt-BR",
            "ja-JP",
            "ko-KR",
            "zh-CN",
        ]
    )
    preferred_language: str = "en-US"


@dataclass(frozen=True)
class PollyConfig:
    voice_id: str = "Tiffany"
    engine: str = "generative"
    language_code: str = "en-US"
    output_format: str = "pcm"


@dataclass(frozen=True)
class AppConfig:
    aws: AwsConfig = field(default_factory=AwsConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    polly: PollyConfig = field(default_factory=PollyConfig)


def load_config(path: Path) -> AppConfig:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return from_dict(data)


def from_dict(data: dict[str, Any]) -> AppConfig:
    return AppConfig(
        aws=AwsConfig(**(data.get("aws") or {})),
        audio=AudioConfig(**(data.get("audio") or {})),
        translator=TranslatorConfig(**(data.get("translator") or {})),
        polly=PollyConfig(**(data.get("polly") or {})),
    )
