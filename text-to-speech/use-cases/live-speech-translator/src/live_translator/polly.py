from __future__ import annotations

import boto3

from .config import AudioConfig, PollyConfig


class PollySynthesizer:
    def __init__(self, region: str, polly: PollyConfig, audio: AudioConfig):
        self._client = boto3.client("polly", region_name=region)
        self._polly = polly
        self._audio = audio

    def synthesize_pcm(self, text: str) -> bytes:
        response = self._client.synthesize_speech(
            Text=text,
            TextType="text",
            OutputFormat=self._polly.output_format,
            VoiceId=self._polly.voice_id,
            Engine=self._polly.engine,
            SampleRate=str(self._audio.sample_rate),
            LanguageCode=self._polly.language_code,
        )
        stream = response.get("AudioStream")
        if stream is None:
            raise RuntimeError("Amazon Polly response did not include AudioStream")
        try:
            return stream.read()
        finally:
            stream.close()
