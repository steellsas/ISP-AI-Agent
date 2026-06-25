"""
gTTS text-to-speech adapter — Google Translate TTS behind `TTSProvider`.

A simple, free starting voice with decent Lithuanian. Returns MP3 bytes; the
caller (a Transport) decides what to do with them. Needs network access (it
calls Google), so integration tests that actually synthesize are guarded.

The `gtts` import is deferred so constructing this adapter is cheap and works
without the optional `voice` dependency installed (Protocol-conformance tests
don't need the engine). Swap to Azure / Piper later behind the same seam.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator

logger = logging.getLogger(__name__)


class GTTSProvider:
    """`TTSProvider` backed by gTTS (Google Translate TTS). Emits MP3 bytes."""

    def __init__(
        self,
        *,
        default_language: str = "lt",
        tld: str = "com",
        slow: bool = False,
    ):
        """
        Args:
            default_language: ISO code used when `synthesize(language=None)`.
            tld: Google domain (affects accent/availability for some locales).
            slow: Speak slowly (gTTS option).
        """
        self._default_language = default_language
        self._tld = tld
        self._slow = slow

    def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Return MP3 audio bytes speaking `text` (empty text -> empty bytes)."""
        if not text or not text.strip():
            return b""

        from gtts import gTTS  # deferred import (optional dependency)

        lang = language or self._default_language
        buffer = io.BytesIO()
        gTTS(text=text, lang=lang, tld=self._tld, slow=self._slow).write_to_fp(buffer)
        audio = buffer.getvalue()
        logger.debug("TTS synthesized %d bytes for %d chars (lang=%s)", len(audio), len(text), lang)
        return audio

    def stream(self, text: str, *, language: str | None = None) -> Iterator[bytes]:
        """Yield one MP3 blob per sentence (gTTS is per-request, so this is
        sentence-level streaming — the transport plays each as the next renders)."""
        from .sentences import split_sentences

        for sentence in split_sentences(text):
            audio = self.synthesize(sentence, language=language)
            if audio:
                yield audio
