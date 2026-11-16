"""
Real Pipecat AgentCore WebSocket bot.

The AgentCore Runtime container exposes /ws from server.py. Each WebSocket
connection is handed to this module, which builds a Pipecat pipeline:

FastAPIWebsocketTransport -> Amazon Transcribe -> Bedrock -> Amazon Polly ->
FastAPIWebsocketTransport
"""

from __future__ import annotations

import os

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.aws.stt import AWSTranscribeSTTService
from pipecat.services.aws.tts import AWSPollyTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner


DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly banking assistant for AnyBank. "
    "Answer general questions about banking products and services. "
    "You cannot access customer accounts, balances, transactions, or live rates; "
    "if asked, say so and suggest the customer contact AnyBank directly. "
    "Never invent account details or numbers. "
    "Be warm, conversational, and concise. Keep responses to two or three sentences. "
    "Do not use markdown, emojis, or characters that are awkward when read aloud."
)


def _language() -> Language | str:
    configured = os.getenv("TRANSCRIBE_LANGUAGE", "en-US")
    if configured.lower() in {"en", "en-us", "en_us"}:
        return Language.EN
    return configured


async def run_bot(websocket_client) -> None:
    """Create and run one Pipecat worker for a single AgentCore WebSocket."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    model = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
    voice = os.getenv("POLLY_VOICE_ID", "Tiffany")
    polly_engine = os.getenv("POLLY_ENGINE", "generative")
    input_sample_rate = int(os.getenv("AUDIO_INPUT_SAMPLE_RATE", os.getenv("AUDIO_SAMPLE_RATE", "16000")))
    output_sample_rate = int(os.getenv("AUDIO_OUTPUT_SAMPLE_RATE", "24000"))
    audio_out_10ms_chunks = int(os.getenv("AUDIO_OUT_10MS_CHUNKS", "4"))
    system_prompt = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)

    logger.info(
        "Starting Pipecat AgentCore cascade: Transcribe -> Bedrock -> Polly "
        f"(region={region}, model={model}, voice={voice})"
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_sample_rate=input_sample_rate,
            audio_out_enabled=True,
            audio_out_sample_rate=output_sample_rate,
            audio_out_10ms_chunks=audio_out_10ms_chunks,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )

    stt = AWSTranscribeSTTService(
        region=region,
        sample_rate=input_sample_rate,
        settings=AWSTranscribeSTTService.Settings(
            language=_language(),
            partial_results_stability=os.getenv("TRANSCRIBE_PARTIAL_STABILITY", "high"),
        ),
    )

    llm_settings = {
        "model": model,
        "system_instruction": system_prompt,
        "max_tokens": int(os.getenv("BEDROCK_MAX_TOKENS", "512")),
        "temperature": float(os.getenv("BEDROCK_TEMPERATURE", "0.4")),
    }
    if os.getenv("BEDROCK_LATENCY"):
        llm_settings["latency"] = os.getenv("BEDROCK_LATENCY")

    llm = AWSBedrockLLMService(
        aws_region=region,
        settings=AWSBedrockLLMService.Settings(**llm_settings),
    )

    tts = AWSPollyTTSService(
        region=region,
        sample_rate=output_sample_rate,
        settings=AWSPollyTTSService.Settings(
            voice=voice,
            engine=polly_engine,
        ),
    )

    context = LLMContext(
        messages=[
            {
                "role": "user",
                "content": "Briefly greet the user and ask how you can help.",
            }
        ]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(sample_rate=input_sample_rate),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=input_sample_rate,
            audio_out_sample_rate=output_sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client) -> None:
        logger.info("Pipecat WebSocket client connected")
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client) -> None:
        logger.info("Pipecat WebSocket client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.run(worker)
