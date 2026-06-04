"""TTS port — text-to-speech. (Phase 3; no implementation yet.)"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    """A swappable text-to-speech backend.

    e.g. gTTS, Azure, or local Piper. Returns encoded audio bytes; the caller
    (a Transport) decides the wire format. Voice quality can improve later by
    swapping the adapter — the core never changes.
    """

    def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Return encoded audio bytes speaking ``text``."""
        ...
