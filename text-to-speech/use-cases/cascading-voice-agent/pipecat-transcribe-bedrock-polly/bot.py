"""
Pipecat cascading voice agent.

Uses Pipecat's standard pipeline service adapters:
transport input -> Amazon Transcribe -> Amazon Bedrock -> Amazon Polly ->
transport output, with placeholder banking tools registered for Bedrock
function calling.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.aws.stt import AWSTranscribeSTTService
from pipecat.services.aws.tts import AWSPollyTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams


load_dotenv(override=True)

DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly banking assistant for AnyBank. "
    "Help customers with account inquiries, transactions, mortgages, and general questions. "
    "Be warm, conversational, and concise. Keep responses to two or three sentences. "
    "Do not use markdown, emojis, or characters that are awkward when read aloud."
)


# Placeholder banking tools (same as the LiveKit variant). Replace the handler
# bodies with real service integrations before using this beyond a demo.
async def get_account_balance(params: FunctionCallParams) -> None:
    """Get the balance for a customer account."""
    account_id = params.arguments.get("account_id", "unknown")
    await params.result_callback(f"Account {account_id} has a balance of $4,231.56.")


async def get_recent_transactions(params: FunctionCallParams) -> None:
    """Get recent transactions for a customer account."""
    account_id = params.arguments.get("account_id", "unknown")
    count = params.arguments.get("count", 5)
    await params.result_callback(
        f"Last {count} transactions for account {account_id}: "
        "Coffee Shop $4.50, Grocery Store $62.30, Gas Station $45.00, "
        "Online Transfer -$200.00, Direct Deposit +$3,200.00."
    )


async def get_mortgage_rates(params: FunctionCallParams) -> None:
    """Get current mortgage rates."""
    await params.result_callback(
        "Current rates: 30-year fixed 6.75%, 15-year fixed 5.99%, 5/1 ARM 6.25%."
    )


TOOLS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            name="get_account_balance",
            description="Get the balance for a customer account.",
            properties={"account_id": {"type": "string", "description": "The customer's account ID."}},
            required=["account_id"],
        ),
        FunctionSchema(
            name="get_recent_transactions",
            description="Get recent transactions for a customer account.",
            properties={
                "account_id": {"type": "string", "description": "The customer's account ID."},
                "count": {"type": "integer", "description": "Number of transactions to return (default 5)."},
            },
            required=["account_id"],
        ),
        FunctionSchema(
            name="get_mortgage_rates",
            description="Get current mortgage rates.",
            properties={},
            required=[],
        ),
    ]
)

TOOL_HANDLERS = {
    "get_account_balance": get_account_balance,
    "get_recent_transactions": get_recent_transactions,
    "get_mortgage_rates": get_mortgage_rates,
}


def _language() -> Language | str:
    """Return a Pipecat language enum when the configured language is known."""
    configured = os.getenv("TRANSCRIBE_LANGUAGE", "en-US")
    if configured.lower().startswith("en"):
        return Language.EN
    return configured


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Build and run the Pipecat STT -> LLM -> TTS pipeline."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    model = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
    latency = os.getenv("BEDROCK_LATENCY") or None
    voice = os.getenv("POLLY_VOICE_ID", "Joanna")

    logger.info("Starting Pipecat cascade: Transcribe -> Bedrock -> Polly")

    stt = AWSTranscribeSTTService(
        region=region,
        sample_rate=16000,
        settings=AWSTranscribeSTTService.Settings(
            language=_language(),
        ),
    )

    llm = AWSBedrockLLMService(
        aws_region=region,
        settings=AWSBedrockLLMService.Settings(
            model=model,
            system_instruction=os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            max_tokens=512,
            latency=latency,
            additional_model_request_fields={
                "reasoningConfig": {
                    "type": "enabled",
                    "maxReasoningEffort": "low",
                }
            },
        ),
    )
    for name, handler in TOOL_HANDLERS.items():
        llm.register_function(name, handler)

    tts = AWSPollyTTSService(
        region=region,
        sample_rate=16000,
        settings=AWSPollyTTSService.Settings(
            voice=voice,
            engine=os.getenv("POLLY_ENGINE", "generative"),
        ),
    )

    messages = [
        {
            "role": "user",
            "content": "Start by briefly greeting the user and asking how you can help.",
        },
    ]
    context = LLMContext(messages=messages, tools=TOOLS)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
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

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport: BaseTransport, client) -> None:
        logger.info("Client connected")
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport: BaseTransport, client) -> None:
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments) -> None:
    """Pipecat runner entrypoint."""
    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
