"""All-AWS voice pipeline: Transcribe (STT) -> Bedrock (LLM) -> Polly (TTS).

The pipeline runs locally against the machine's microphone and speaker, using
Amazon services for every step of the conversation. A Reachy Mini driver is
appended so the robot can react (poses/emotions) to what the assistant says.

Pipeline diagram (frames flow left to right)::

    transport.input()   # mic audio in
      -> stt            # Amazon Transcribe streaming
      -> user_agg       # user-side context aggregator (owns the VAD analyzer)
      -> llm            # Amazon Bedrock
      -> tts            # Amazon Polly
      -> transport.output()   # speaker audio out
      -> driver         # ReachyDriver: move the robot to match the speech
      -> assistant_agg  # assistant-side context aggregator

Notes for pipecat 1.7.x:

* This uses the NEW universal-context API (``LLMContext`` +
  ``LLMContextAggregatorPair``), not the old 0.0.x service-specific context.
* The Silero VAD analyzer now lives on the *user* aggregator
  (``LLMUserAggregatorParams(vad_analyzer=...)``), not on the transport.
* The robot driver is placed AFTER ``transport.output()`` so it observes the
  same TTS/speech frames the speaker plays, and reacts in step with the audio.
"""

from __future__ import annotations

import logging

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.transcriptions.language import Language
from pipecat.services.aws.stt import AWSTranscribeSTTService
from pipecat.services.aws.tts import AWSPollyTTSService
from pipecat.services.aws.llm import AWSBedrockLLMService

from voicebot.prompts import DEFAULT_SYSTEM_PROMPT, GREETING_INSTRUCTION

logger = logging.getLogger(__name__)


# The Reachy Mini Lite exposes its microphone array and its speaker as a single
# USB sound card with this name. We look it up by name because PyAudio device
# indices shift whenever USB audio gear is plugged in or removed.
REACHY_AUDIO_DEVICE = "Reachy Mini Audio"


def find_device_index(name: str, *, want_input: bool) -> int | None:
    """PyAudio index of the first device matching ``name``, or None if absent.

    ``want_input`` picks the direction to match on, since one card can expose
    both. Returning None lets the transport fall back to the system default.
    """

    import pyaudio  # local import: keeps PortAudio off this module's import path

    channels = "maxInputChannels" if want_input else "maxOutputChannels"
    pa = pyaudio.PyAudio()
    try:
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if name.lower() in str(info["name"]).lower() and int(info[channels] or 0) > 0:
                return index
    finally:
        pa.terminate()
    return None


def describe_device(index: int | None, *, want_input: bool) -> str:
    """Human-readable name for a PyAudio device index, for the startup log.

    ``index`` of None means "let PortAudio pick", so resolve the OS default and
    name it — otherwise the log says "system default" and you cannot tell which
    microphone actually fed the pipeline.
    """

    import pyaudio  # local import: keeps PortAudio off this module's import path

    pa = pyaudio.PyAudio()
    try:
        if index is None:
            info = (
                pa.get_default_input_device_info()
                if want_input
                else pa.get_default_output_device_info()
            )
            return f"index {info['index']} '{info['name']}' (OS default)"
        return f"index {index} '{pa.get_device_info_by_index(index)['name']}'"
    except Exception:  # noqa: BLE001 - a log line must never break startup
        return "index system default" if index is None else f"index {index}"
    finally:
        pa.terminate()


def build_transport(cfg) -> LocalAudioTransport:
    """Build the local mic/speaker transport from ``cfg``.

    Output is always the robot's own speaker; input is the robot's mic array or
    the host's default microphone, per ``audio.mic``. Explicit device indices in
    the config win over both.
    """

    input_index = cfg.audio.input_device_index
    if input_index is None and cfg.audio.mic == "reachy":
        input_index = find_device_index(REACHY_AUDIO_DEVICE, want_input=True)
        if input_index is None:
            logger.warning(
                "No '%s' input device found; using the system default microphone. "
                "Set audio.mic: laptop in config.yaml to select the host mic.",
                REACHY_AUDIO_DEVICE,
            )

    output_index = cfg.audio.output_device_index
    if output_index is None:
        output_index = find_device_index(REACHY_AUDIO_DEVICE, want_input=False)
        if output_index is None:
            logger.warning(
                "No '%s' output device found; using the system default speaker.",
                REACHY_AUDIO_DEVICE,
            )

    logger.info(
        "Audio devices: mic=%s -> %s | speaker -> %s",
        cfg.audio.mic,
        describe_device(input_index, want_input=True),
        describe_device(output_index, want_input=False),
    )

    return LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=cfg.stt.sample_rate,
            audio_out_sample_rate=cfg.tts.sample_rate,
            input_device_index=input_index,
            output_device_index=output_index,
        )
    )


def _language(code: str) -> Language:
    """Resolve a BCP-47-ish ``code`` to a pipecat ``Language`` (fallback: EN_US)."""

    try:
        return Language(code)
    except (ValueError, KeyError):
        return Language.EN_US


def build_stt(cfg) -> AWSTranscribeSTTService:
    """Build the Amazon Transcribe streaming STT service.

    Credentials resolve from the environment / default botocore chain; we never
    pass secrets explicitly.
    """

    return AWSTranscribeSTTService(
        region=cfg.region,
        sample_rate=cfg.stt.sample_rate,
        settings=AWSTranscribeSTTService.Settings(language=_language(cfg.stt.language)),
    )


def build_llm(cfg) -> AWSBedrockLLMService:
    """Build the Amazon Bedrock LLM service."""

    system_prompt = cfg.llm.system_prompt or DEFAULT_SYSTEM_PROMPT
    # temperature / latency may be None (e.g. for reasoning models like Grok that
    # reject them). pipecat's Bedrock service omits `temperature` when None and
    # omits `performanceConfig` unless latency is "standard"/"optimized".
    return AWSBedrockLLMService(
        aws_region=cfg.region,
        settings=AWSBedrockLLMService.Settings(
            model=cfg.llm.model_id,
            system_instruction=system_prompt,
            max_tokens=cfg.llm.max_tokens,
            temperature=cfg.llm.temperature,
            latency=cfg.llm.latency,
        ),
    )


def build_tts(cfg) -> AWSPollyTTSService:
    """Build the Amazon Polly TTS service."""

    return AWSPollyTTSService(
        region=cfg.region,
        sample_rate=cfg.tts.sample_rate,
        settings=AWSPollyTTSService.Settings(
            voice=cfg.tts.voice,
            engine=cfg.tts.engine,
            language=Language.EN_US,
            pitch=cfg.tts.pitch,
            rate=cfg.tts.rate,
            volume=cfg.tts.volume,
        ),
    )


async def run_voicebot(cfg, robot) -> None:
    """Assemble and run the all-AWS voice pipeline until interrupted."""

    transport = build_transport(cfg)
    stt = build_stt(cfg)
    llm = build_llm(cfg)
    tts = build_tts(cfg)

    # Universal context shared by the user/assistant aggregator pair. The VAD
    # analyzer lives on the user aggregator in pipecat 1.7 (not the transport).
    context = LLMContext()
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=cfg.vad.stop_secs)),
            # Ignore the mic while the robot is speaking: the robot's speaker and
            # mic share one body and there is no echo cancellation here, so
            # otherwise Polly's own voice is transcribed as the user's reply.
            user_mute_strategies=[AlwaysUserMuteStrategy()],
        ),
    )

    # The robot driver sits AFTER transport.output() so it reacts to the same
    # speech frames the speaker plays. Imported here to keep pipecat-free
    # importers (e.g. preflight checks) working.
    from voicebot.robot.controller import ReachyDriver

    driver = ReachyDriver(
        robot, cfg.robot.emotions, cfg.robot.gestures,
        emotion_sound=cfg.robot.emotion_sound,
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_agg,
            llm,
            tts,
            transport.output(),
            driver,
            assistant_agg,
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=True))

    # Make the bot greet first: seed a developer instruction and kick the LLM.
    context.add_message({"role": "developer", "content": GREETING_INSTRUCTION})
    await task.queue_frames([LLMRunFrame()])

    await PipelineRunner().run(task)
