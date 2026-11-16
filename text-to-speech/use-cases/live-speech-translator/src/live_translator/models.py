from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptPhrase:
    text: str
    source_language: str
    transcribe_language: str | None = None
