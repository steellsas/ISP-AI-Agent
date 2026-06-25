"""TTS port — text-to-speech."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    """A swappable text-to-speech backend.

    e.g. gTTS, edge-tts, or local Piper. Returns encoded audio bytes; the caller
    (a Transport) decides the wire format. Voice quality can improve later by
    swapping the adapter — the core never changes.
    """

    def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Return encoded audio bytes speaking ``text``."""
        ...


@runtime_checkable
class StreamingTTSProvider(TTSProvider, Protocol):
    """A `TTSProvider` that can also STREAM audio in chunks as they are produced,
    so a transport can start playing before the whole reply is synthesized
    (latency masking, Pillar C). Each yielded chunk is a self-contained, decodable
    audio blob (one per sentence) — adapters that cannot stream natively chunk by
    sentence; the overlap (synthesize ahead while playing) lives in the transport.
    """

    def stream(self, text: str, *, language: str | None = None) -> Iterator[bytes]:
        """Yield encoded audio chunks (one decodable blob per sentence)."""
        ...
