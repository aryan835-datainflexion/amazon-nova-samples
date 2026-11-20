"""
LiveKit streaming cascading voice agent.

Runs a WebRTC voice agent with Amazon Transcribe Streaming for STT,
Amazon Bedrock ConverseStream for LLM output, and Amazon Polly for TTS via
the LiveKit AWS plugin.
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.plugins import aws, silero


load_dotenv()

logger = logging.getLogger("livekit-cascading-voice-agent")
logger.setLevel(logging.INFO)

DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly banking assistant for AnyBank. "
    "Help customers with account inquiries, transactions, mortgages, and general questions. "
    "Be warm, conversational, and concise. Keep responses to two or three sentences. "
    "Do not use markdown, emojis, or characters that are awkward when read aloud."
)


class AnyBankAgent(Agent):
    """Small sample agent with placeholder banking tools."""

    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)

    @function_tool()
    async def get_account_balance(self, context: RunContext, account_id: str) -> str:
        """Get the balance for a customer account."""
        return f"Account {account_id} has a balance of $4,231.56."

    @function_tool()
    async def get_recent_transactions(
        self,
        context: RunContext,
        account_id: str,
        count: int = 5,
    ) -> str:
        """Get recent transactions for a customer account."""
        return (
            f"Last {count} transactions for account {account_id}: "
            "Coffee Shop $4.50, Grocery Store $62.30, Gas Station $45.00, "
            "Online Transfer -$200.00, Direct Deposit +$3,200.00."
        )

    @function_tool()
    async def get_mortgage_rates(self, context: RunContext) -> str:
        """Get current mortgage rates."""
        return "Current rates: 30-year fixed 6.75%, 15-year fixed 5.99%, 5/1 ARM 6.25%."


def _metadata(ctx: JobContext) -> dict:
    """Read optional JSON metadata from a LiveKit dispatch request."""
    raw = getattr(ctx.job, "metadata", "") or ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ignoring non-JSON job metadata")
        return {}


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """LiveKit job entrypoint; one AgentSession is created per dispatched room."""
    metadata = _metadata(ctx)

    region = metadata.get("region") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    model = metadata.get("model") or os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
    voice = metadata.get("voice") or os.getenv("POLLY_VOICE_ID", "Joanna")
    language = metadata.get("language") or os.getenv("TRANSCRIBE_LANGUAGE", "en-US")
    instructions = metadata.get("system_prompt") or os.getenv("SYSTEM_PROMPT") or DEFAULT_SYSTEM_PROMPT

    ctx.log_context_fields = {
        "voice_agent": "livekit-streaming-transcribe-bedrock-polly",
        "bedrock_model": model,
        "aws_region": region,
    }

    logger.info("Starting LiveKit streaming cascade: Transcribe -> Bedrock -> Polly")

    session = AgentSession(
        stt=aws.STT(
            region=region,
            sample_rate=16000,
            language=language,
            enable_partial_results_stabilization=True,
            partial_results_stability="high",
        ),
        llm=aws.LLM(
            model=model,
            region=region,
            max_output_tokens=512,
            additional_request_fields={
                "reasoningConfig": {
                    "type": "enabled",
                    "maxReasoningEffort": "low",
                }
            },
        ),
        tts=aws.TTS(
            voice=voice,
            sample_rate=16000,
            region=region,
            speech_engine=os.getenv("POLLY_ENGINE", "generative"),
        ),
        vad=silero.VAD.load(),
        transcription_timeout=5.0,
    )

    await session.start(
        room=ctx.room,
        agent=AnyBankAgent(instructions=instructions),
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
            text_input=True,
            text_output=True,
        ),
    )

    await session.generate_reply(
        instructions="Briefly greet the user and ask how you can help."
    )


if __name__ == "__main__":
    cli.run_app(server)
