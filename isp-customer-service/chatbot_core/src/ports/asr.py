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
        context: str | None = None,
    ) -> str:
        """Return the recognised text for ``audio``.

        ``context`` (VOICE_PLAN V1) is per-turn biasing text — the agent's last
        question and the expected answer vocabulary — appended to the adapter's
        static domain prompt so short/garbled replies decode toward what the
        conversation expects. Adapters may ignore it."""
        ...
