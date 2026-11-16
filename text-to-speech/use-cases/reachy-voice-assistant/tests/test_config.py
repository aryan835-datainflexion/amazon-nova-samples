"""Config loading tests. No AWS, no pipecat, no robot required."""

from __future__ import annotations

import textwrap

import pytest

from voicebot.config import Config, config_from_dict, load_config

# The config layer applies environment-variable overrides on top of file/defaults.
# Most tests assert on file/default values, so clear those override vars first to
# keep the suite hermetic regardless of the developer's / CI shell environment.
_OVERRIDE_ENV = ("AWS_REGION", "BEDROCK_MODEL_ID", "POLLY_VOICE", "ROBOT_BACKEND", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def _clear_override_env(monkeypatch):
    for var in _OVERRIDE_ENV:
        monkeypatch.delenv(var, raising=False)


def test_defaults_are_runnable():
    cfg = config_from_dict({})
    assert cfg.region == "us-east-1"
    assert cfg.stt.sample_rate == 16000
    assert cfg.llm.provider == "bedrock"
    assert cfg.llm.model_id.startswith("us.amazon.nova") or "claude" in cfg.llm.model_id
    assert cfg.tts.voice == "Ivy"
    assert cfg.robot.emotion_sound is True
    assert cfg.robot.backend in {"reachy", "fake"}
    assert cfg.robot.emotions.on_start == "welcoming1"


def test_nested_overrides_from_dict():
    data = {
        "aws": {"region": "us-west-2"},
        "llm": {"model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "temperature": 0.2},
        "tts": {"voice": "Matthew", "engine": "generative"},
        "robot": {"backend": "fake", "emotions": {"on_error": None}},
        "vad": {"stop_secs": 1.2},
    }
    cfg = config_from_dict(data)
    assert cfg.region == "us-west-2"
    assert "claude" in cfg.llm.model_id
    assert cfg.llm.temperature == 0.2
    assert cfg.tts.voice == "Matthew"
    assert cfg.tts.engine == "generative"
    assert cfg.robot.backend == "fake"
    assert cfg.robot.emotions.on_error is None
    assert cfg.robot.emotions.on_start == "welcoming1"  # untouched default
    assert cfg.vad.stop_secs == 1.2


def test_voice_style_preset_overrides_fields():
    # The "expressive" preset must win over the per-field values.
    cfg = config_from_dict({"tts": {"style": "expressive", "voice": "Ivy", "engine": "standard",
                                     "pitch": "+50%"}})
    assert cfg.tts.voice == "Ruth"
    assert cfg.tts.engine == "generative"
    assert cfg.tts.pitch is None and cfg.tts.rate is None  # generative has no prosody


def test_voice_style_null_uses_fields():
    cfg = config_from_dict({"tts": {"style": None, "voice": "Ivy", "engine": "standard",
                                    "pitch": "+30%"}})
    assert cfg.tts.voice == "Ivy" and cfg.tts.engine == "standard" and cfg.tts.pitch == "+30%"


def test_unknown_voice_style_raises():
    with pytest.raises(ValueError):
        config_from_dict({"tts": {"style": "nope"}})


def test_env_overrides_take_precedence(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
    monkeypatch.setenv("POLLY_VOICE", "Ruth")
    monkeypatch.setenv("ROBOT_BACKEND", "fake")
    cfg = config_from_dict({"aws": {"region": "us-east-1"}, "tts": {"voice": "Joanna"}})
    assert cfg.region == "eu-west-1"
    assert cfg.llm.model_id == "us.amazon.nova-lite-v1:0"
    assert cfg.tts.voice == "Ruth"
    assert cfg.robot.backend == "fake"


def test_mic_source_defaults_to_reachy():
    cfg = config_from_dict({})
    assert cfg.audio.mic == "reachy"
    assert cfg.audio.input_device_index is None
    assert cfg.audio.output_device_index is None


def test_mic_source_laptop_from_yaml():
    cfg = config_from_dict({"audio": {"mic": "laptop"}})
    assert cfg.audio.mic == "laptop"


def test_unknown_mic_source_raises():
    with pytest.raises(ValueError):
        config_from_dict({"audio": {"mic": "labtop"}})


def test_bad_section_type_raises():
    with pytest.raises(ValueError):
        config_from_dict({"llm": "not-a-mapping"})


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "does-not-exist.yaml")
    assert isinstance(cfg, Config)
    assert cfg.region == "us-east-1"


def test_load_config_reads_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        textwrap.dedent(
            """
            aws:
              region: ap-south-1
            robot:
              backend: fake
            """
        ),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.region == "ap-south-1"
    assert cfg.robot.backend == "fake"
