"""Configuration for the Reachy voice assistant.

Values are loaded from a YAML file (see ``config.yaml``) and then overridden by a
small set of environment variables so the same config works across machines and
CI without editing files. Everything has a sensible default, so an empty/missing
config file still yields a runnable configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class STTConfig:
    """Amazon Transcribe streaming STT settings."""

    language: str = "en-US"
    # Amazon Transcribe streaming (and pipecat's AWSTranscribeSTTService) only
    # accept 8000 or 16000 Hz; other values are clamped to 16000.
    sample_rate: int = 16000


@dataclass
class LLMConfig:
    """Amazon Bedrock LLM settings.

    Default is Anthropic Claude Sonnet 4.5 (low latency, strong instruction
    following for a voice assistant). Amazon Nova, Claude Opus 4.8, Grok, and
    OpenAI are documented as alternatives in config.yaml.
    """

    provider: str = "bedrock"  # only "bedrock" is supported in this sample
    model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    # None -> use the built-in default system prompt from prompts.py
    system_prompt: str | None = None
    max_tokens: int = 512
    # Some models (e.g. reasoning models like xAI Grok) reject `temperature` and
    # `performanceConfig`. Set either to null in YAML to omit it from the request.
    temperature: float | None = 0.6
    # None omits performanceConfig (safe everywhere). "standard"/"optimized" enable
    # Bedrock latency-optimized inference, which only some model/region combos
    # support (e.g. Claude Sonnet 4.5 in us-west-2 rejects it).
    latency: str | None = None


@dataclass
class TTSConfig:
    """Amazon Polly TTS settings.

    The "voice style" is a voice + engine (see the presets in config.yaml). The
    optional prosody fields shape it further — note ``pitch`` only affects the
    standard engine, so a higher/"baby" voice needs ``engine: standard``.
    """

    # Optional named OVERRIDE preset (see VOICE_STYLE_PRESETS). When set, it
    # replaces the voice/engine/pitch/rate fields below. Leave it null to use
    # those fields directly (that is the default, hand-tunable voice).
    style: str | None = None
    # The base voice, used when style is null. Defaults to the youngest voice
    # Polly offers — child voice "Ivy" on the standard engine, pitched up (Polly
    # has no true toddler voice; pitch only works on the standard engine).
    voice: str = "Ivy"  # child voice (young girl)
    engine: str = "standard"  # standard | neural | generative (pitch needs standard)
    pitch: str | None = "+50%"  # higher = younger; e.g. "+30%" is milder, null = none
    rate: str | None = "90%"  # slightly slower, more child-like
    volume: str | None = None  # e.g. "loud" (applied regardless of style)
    sample_rate: int = 16000


# Named voice-style presets — shortcuts that OVERRIDE the individual
# voice/engine/pitch/rate fields. There is no "youngest" preset on purpose: the
# default fields already are the youngest voice, so just leave tts.style null for
# that. "expressive" uses Polly's most natural/emotive GENERATIVE engine, which
# does not support pitch, so it is an adult voice (not a child one).
VOICE_STYLE_PRESETS: dict[str, dict] = {
    "child":        {"voice": "Ivy",     "engine": "neural",     "pitch": None, "rate": None},
    "expressive":   {"voice": "Ruth",    "engine": "generative", "pitch": None, "rate": None},
    "adult_female": {"voice": "Joanna",  "engine": "neural",     "pitch": None, "rate": None},
    "adult_male":   {"voice": "Matthew", "engine": "neural",     "pitch": None, "rate": None},
}


@dataclass
class EmotionConfig:
    """Names of Reachy Mini emotion-library moves to play at key moments.

    Set any of these to null in YAML to disable that cue.
    """

    on_start: str | None = "welcoming1"
    on_error: str | None = "confused1"
    on_sleep: str | None = "mini-deep-sleep"


@dataclass
class RobotConfig:
    backend: str = "reachy"  # "reachy" (SDK) | "fake" (no hardware)
    gestures: bool = True  # play emotion-library moves in addition to poses
    # Play the emotion move's OWN recorded audio clip (the robot's cute
    # vocalizations) in addition to the motion? Applies to the error/sleep
    # emotions. The startup (on_start) emotion is ALWAYS motion-only, because it
    # coincides with Polly's spoken greeting and its clip would talk over it.
    emotion_sound: bool = True
    emotions: EmotionConfig = field(default_factory=EmotionConfig)


@dataclass
class AudioConfig:
    """Local microphone/speaker device selection.

    The speaker is always the robot's own USB sound card. ``mic`` chooses where
    the audio comes *from*: "reachy" (the robot's built-in array) or "laptop"
    (the host's default input).

    "laptop" is a workaround for two problems with the robot's array: it picks
    up speech poorly, and sitting inches from the robot's speaker it also hears
    Polly's own replies, which Transcribe then re-transcribes (the assistant
    talks to itself). A separate host mic avoids both.

    The device indices are an escape hatch and win over ``mic`` when set; None
    means "resolve automatically".
    """

    mic: str = "reachy"  # reachy | laptop
    input_device_index: int | None = None
    output_device_index: int | None = None


# Valid values for audio.mic.
MIC_SOURCES = ("reachy", "laptop")


@dataclass
class VADConfig:
    # Silence (seconds) after speech before the user's turn is considered done.
    stop_secs: float = 0.8


@dataclass
class Config:
    region: str = "us-east-1"
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    robot: RobotConfig = field(default_factory=RobotConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    log_level: str = "INFO"


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a nested mapping from ``data``, tolerating missing/None sections."""

    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Config section '{key}' must be a mapping, got {type(value).__name__}")
    return value


def _opt_float(value: Any) -> float | None:
    """Coerce to float, but preserve an explicit null (used to omit the field)."""

    return None if value is None else float(value)


def config_from_dict(data: dict[str, Any] | None) -> Config:
    """Build a :class:`Config` from a plain dict (e.g. parsed YAML)."""

    data = data or {}
    aws = _section(data, "aws")
    stt = _section(data, "stt")
    llm = _section(data, "llm")
    tts = _section(data, "tts")
    robot = _section(data, "robot")
    emotions = _section(robot, "emotions")
    audio = _section(data, "audio")
    vad = _section(data, "vad")
    logging_ = _section(data, "logging")

    cfg = Config(
        region=aws.get("region", Config.region),
        stt=STTConfig(
            language=stt.get("language", STTConfig.language),
            sample_rate=int(stt.get("sample_rate", STTConfig.sample_rate)),
        ),
        llm=LLMConfig(
            provider=llm.get("provider", LLMConfig.provider),
            model_id=llm.get("model_id", LLMConfig.model_id),
            system_prompt=llm.get("system_prompt", LLMConfig.system_prompt),
            max_tokens=int(llm.get("max_tokens", LLMConfig.max_tokens)),
            temperature=_opt_float(llm.get("temperature", LLMConfig.temperature)),
            latency=llm.get("latency", LLMConfig.latency),
        ),
        tts=TTSConfig(
            style=tts.get("style", TTSConfig.style),
            voice=tts.get("voice", TTSConfig.voice),
            engine=tts.get("engine", TTSConfig.engine),
            pitch=tts.get("pitch", TTSConfig.pitch),
            rate=tts.get("rate", TTSConfig.rate),
            volume=tts.get("volume", TTSConfig.volume),
            sample_rate=int(tts.get("sample_rate", TTSConfig.sample_rate)),
        ),
        robot=RobotConfig(
            backend=robot.get("backend", RobotConfig.backend),
            gestures=bool(robot.get("gestures", RobotConfig.gestures)),
            emotion_sound=bool(robot.get("emotion_sound", RobotConfig.emotion_sound)),
            emotions=EmotionConfig(
                on_start=emotions.get("on_start", EmotionConfig.on_start),
                on_error=emotions.get("on_error", EmotionConfig.on_error),
                on_sleep=emotions.get("on_sleep", EmotionConfig.on_sleep),
            ),
        ),
        audio=AudioConfig(
            mic=audio.get("mic", AudioConfig.mic),
            input_device_index=audio.get("input_device_index", AudioConfig.input_device_index),
            output_device_index=audio.get("output_device_index", AudioConfig.output_device_index),
        ),
        vad=VADConfig(stop_secs=float(vad.get("stop_secs", VADConfig.stop_secs))),
        log_level=logging_.get("level", Config.log_level),
    )
    _apply_voice_style_preset(cfg.tts)
    if cfg.audio.mic not in MIC_SOURCES:
        raise ValueError(f"Unknown audio.mic '{cfg.audio.mic}'; choose from {list(MIC_SOURCES)}")
    return _apply_env_overrides(cfg)


def _apply_voice_style_preset(tts_cfg: TTSConfig) -> None:
    """If ``tts.style`` names a preset, overwrite voice/engine/pitch/rate with it."""

    if not tts_cfg.style:
        return
    preset = VOICE_STYLE_PRESETS.get(tts_cfg.style)
    if preset is None:
        raise ValueError(
            f"Unknown tts.style '{tts_cfg.style}'; choose from {sorted(VOICE_STYLE_PRESETS)}"
        )
    tts_cfg.voice = preset["voice"]
    tts_cfg.engine = preset["engine"]
    tts_cfg.pitch = preset["pitch"]
    tts_cfg.rate = preset["rate"]


def _apply_env_overrides(cfg: Config) -> Config:
    """Apply environment-variable overrides for the handful of fields that
    commonly change between environments."""

    if os.getenv("AWS_REGION"):
        cfg.region = os.environ["AWS_REGION"]
    if os.getenv("BEDROCK_MODEL_ID"):
        cfg.llm.model_id = os.environ["BEDROCK_MODEL_ID"]
    if os.getenv("POLLY_VOICE"):
        cfg.tts.voice = os.environ["POLLY_VOICE"]
    if os.getenv("ROBOT_BACKEND"):
        cfg.robot.backend = os.environ["ROBOT_BACKEND"]
    if os.getenv("LOG_LEVEL"):
        cfg.log_level = os.environ["LOG_LEVEL"]
    return cfg


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load configuration from ``path`` (YAML). Missing file -> all defaults."""

    data: dict[str, Any] = {}
    if path is not None:
        p = Path(path)
        if p.exists():
            with p.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
    return config_from_dict(data)
