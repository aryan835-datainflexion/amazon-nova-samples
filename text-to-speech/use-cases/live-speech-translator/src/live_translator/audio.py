from __future__ import annotations

import asyncio

import sounddevice as sd

from .config import AudioConfig


def format_audio_devices() -> str:
    default_input, default_output = sd.default.device
    lines = ["Available audio devices:"]
    devices = sd.query_devices()
    if not devices:
        lines.append("  None found.")
        return "\n".join(lines)

    for index, device in enumerate(devices):
        roles = []
        if device["max_input_channels"] > 0:
            roles.append("input")
        if device["max_output_channels"] > 0:
            roles.append("output")
        if index == default_input:
            roles.append("default input")
        if index == default_output:
            roles.append("default output")
        lines.append(f"  {index}: {device['name']} ({', '.join(roles) or 'unavailable'})")
    return "\n".join(lines)


def check_audio_devices(config: AudioConfig) -> tuple[str, str]:
    sd.check_input_settings(
        device=config.input_device,
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype=config.dtype,
    )
    sd.check_output_settings(
        device=config.output_device,
        samplerate=config.sample_rate,
        channels=config.channels,
        dtype=config.dtype,
    )
    input_device = sd.query_devices(config.input_device, kind="input")
    output_device = sd.query_devices(config.output_device, kind="output")
    return str(input_device["name"]), str(output_device["name"])


class Microphone:
    def __init__(self, config: AudioConfig):
        self._config = config

    async def chunks(self):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)

        def callback(indata, frames, time_info, status):
            del frames, time_info, status
            chunk = bytes(indata)

            def enqueue():
                if queue.full():
                    _ = queue.get_nowait()
                queue.put_nowait(chunk)

            loop.call_soon_threadsafe(enqueue)

        with sd.RawInputStream(
            device=self._config.input_device,
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            dtype=self._config.dtype,
            blocksize=self._config.mic_block_frames,
            callback=callback,
        ):
            while True:
                yield await queue.get()


class Speaker:
    def __init__(self, config: AudioConfig):
        self._config = config

    def play_pcm(self, pcm: bytes) -> None:
        if not pcm:
            return
        with sd.RawOutputStream(
            device=self._config.output_device,
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            dtype=self._config.dtype,
        ) as stream:
            for offset in range(0, len(pcm), self._config.playback_chunk_bytes):
                stream.write(pcm[offset : offset + self._config.playback_chunk_bytes])
