from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .config import AppConfig
from .models import TranscriptPhrase


@dataclass(frozen=True)
class TranslationResult:
    heard_text: str
    translated_text: str
    source_language: str
    target_language: str


class LiveTranslationPipeline:
    def __init__(self, config: AppConfig):
        from .audio import Microphone, Speaker
        from .polly import PollySynthesizer
        from .transcribe import TranscribeStreamer
        from .translate import TranslateClient

        self._config = config
        self._microphone = Microphone(config.audio)
        self._speaker = Speaker(config.audio)
        self._transcribe = TranscribeStreamer(config.aws.region, config.translator)
        self._translate = TranslateClient(config.aws.region)
        self._polly = PollySynthesizer(config.aws.region, config.polly, config.audio)

    async def run(self) -> None:
        from .transcribe import FinalTranscriptHandler

        phrase_queue: asyncio.Queue[TranscriptPhrase] = asyncio.Queue(
            maxsize=self._config.translator.queue_size
        )
        is_playing = asyncio.Event()
        stream = await self._transcribe.start(self._config.audio.sample_rate)
        handler = FinalTranscriptHandler(
            stream.output_stream,
            phrase_queue,
            self._config.translator.source_language,
        )

        tasks = [
            asyncio.create_task(self._send_microphone_audio(stream, is_playing)),
            asyncio.create_task(handler.handle_events()),
            asyncio.create_task(self._translate_and_speak(phrase_queue, is_playing)),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await _end_input_stream(stream)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_microphone_audio(self, stream, is_playing: asyncio.Event) -> None:
        half_duplex = self._config.translator.mode == "half-duplex"
        async for chunk in self._microphone.chunks():
            if half_duplex and is_playing.is_set():
                chunk = b"\x00" * len(chunk)
            await stream.input_stream.send_audio_event(audio_chunk=chunk)

    async def _translate_and_speak(
        self,
        phrase_queue: asyncio.Queue[TranscriptPhrase],
        is_playing: asyncio.Event,
    ) -> None:
        while True:
            phrase = await phrase_queue.get()
            try:
                result = await self.translate_phrase(phrase)
                print(f"\nheard [{result.source_language}]: {result.heard_text}")
                print(f"{result.target_language}: {result.translated_text}")

                pcm = await asyncio.to_thread(
                    self._polly.synthesize_pcm,
                    result.translated_text,
                )
                is_playing.set()
                try:
                    await asyncio.to_thread(self._speaker.play_pcm, pcm)
                finally:
                    is_playing.clear()
            except Exception as exc:  # noqa: BLE001 - keep live sample running
                print(f"[pipeline error] {exc}")
            finally:
                is_playing.clear()
                phrase_queue.task_done()

    async def translate_phrase(self, phrase: TranscriptPhrase) -> TranslationResult:
        translated = await asyncio.to_thread(
            self._translate.translate_text,
            phrase.text,
            phrase.source_language,
            self._config.translator.target_language,
            self._config.translator.skip_translation_when_source_matches_target,
        )
        return TranslationResult(
            heard_text=phrase.text,
            translated_text=translated,
            source_language=phrase.source_language,
            target_language=self._config.translator.target_language,
        )


async def _end_input_stream(stream) -> None:
    end_stream = getattr(stream.input_stream, "end_stream", None)
    if end_stream is None:
        return
    result = end_stream()
    if asyncio.iscoroutine(result):
        await result
