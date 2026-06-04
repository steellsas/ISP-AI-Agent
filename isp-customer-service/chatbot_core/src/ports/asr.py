"""ASR port — speech-to-text. (Phase 3; no implementation yet.)"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ASRProvider(Protocol):
    """A swappable speech-to-text backend.

    e.g. ``faster-whisper`` running locally or a hosted Whisper API — both hide
    behind this interface so the voice slice (Phase 3) can change engines
    without touching the agent core. ``audio`` is raw PCM/WAV bytes; ``language``
    is an optional ISO hint (e.g. "lt").
    """

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        sample_rate: int = 16_000,
    ) -> str:
        """Return the recognised text for ``audio``."""
        ...
