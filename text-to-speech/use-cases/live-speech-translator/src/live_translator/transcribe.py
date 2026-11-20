from __future__ import annotations

import asyncio

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from .config import TranslatorConfig
from .languages import detected_transcribe_language, transcribe_locale_to_translate_code
from .models import TranscriptPhrase


class FinalTranscriptHandler(TranscriptResultStreamHandler):
    def __init__(
        self,
        output_stream,
        phrase_queue: asyncio.Queue[TranscriptPhrase],
        source_language: str,
    ):
        super().__init__(output_stream)
        self._phrase_queue = phrase_queue
        self._source_language = source_language

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        for result in transcript_event.transcript.results:
            if result.is_partial:
                continue

            detected_locale = detected_transcribe_language(result)
            source = (
                "auto"
                if self._source_language == "auto" and not detected_locale
                else transcribe_locale_to_translate_code(detected_locale or self._source_language)
            )

            for alternative in result.alternatives:
                text = (alternative.transcript or "").strip()
                if text:
                    await self._phrase_queue.put(
                        TranscriptPhrase(
                            text=text,
                            source_language=source,
                            transcribe_language=detected_locale,
                        )
                    )
                    break


class TranscribeStreamer:
    def __init__(self, region: str, config: TranslatorConfig):
        self._client = TranscribeStreamingClient(region=region)
        self._config = config

    async def start(self, sample_rate: int):
        kwargs = build_start_stream_args(self._config, sample_rate)
        return await self._client.start_stream_transcription(**kwargs)


def build_start_stream_args(config: TranslatorConfig, sample_rate: int) -> dict:
    kwargs = {
        "media_sample_rate_hz": sample_rate,
        "media_encoding": "pcm",
    }
    if config.source_language == "auto":
        kwargs["language_code"] = None
        kwargs["language_options"] = config.auto_language_options
        if config.identify_multiple_languages:
            kwargs["identify_multiple_languages"] = True
        else:
            kwargs["identify_language"] = True
            kwargs["preferred_language"] = config.preferred_language
    else:
        kwargs["language_code"] = config.source_language
    return kwargs
