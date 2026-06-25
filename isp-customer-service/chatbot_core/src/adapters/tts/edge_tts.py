"""
edge-tts adapter — Microsoft Edge neural TTS behind `StreamingTTSProvider`.

A free, no-key, neural voice with good Lithuanian (`lt-LT-OnaNeural` /
`lt-LT-LeonasNeural`) that STREAMS audio, so the transport can start playing the
reply before it is fully rendered (Pillar C). Emits MP3 bytes; one decodable blob
per sentence (the per-sentence overlap — render ahead while playing — lives in the
transport).

edge-tts is async (it talks to Microsoft's service over the network); we bridge it
to the sync `TTSProvider` seam with `asyncio.run` per sentence. The `edge_tts`
import is deferred so the adapter constructs without the optional `voice` extra.
Swap to Piper (offline) / Azure / ElevenLabs later behind the same port.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Default voices per language (extend as more locales are added).
_VOICES = {"lt": "lt-LT-OnaNeural", "en": "en-US-AriaNeural"}


class EdgeTTSProvider:
    """`StreamingTTSProvider` backed by edge-tts. Emits MP3 bytes per sentence."""

    def __init__(self, *, default_language: str = "lt", voice: str | None = None):
        """
        Args:
            default_language: ISO code used when `language=None`.
            voice: explicit edge voice (overrides the per-language default).
        """
        self._default_language = default_language
        self._voice = voice

    def _voice_for(self, language: str | None) -> str:
        if self._voice:
            return self._voice
        lang = (language or self._default_language).split("-")[0].lower()
        return _VOICES.get(lang, _VOICES["lt"])

    def _synthesize_one(self, sentence: str, voice: str) -> bytes:
        """Render one sentence to MP3 via edge-tts (async collected to bytes)."""
        import edge_tts  # deferred (optional dependency)

        async def _collect() -> bytes:
            out = bytearray()
            async for chunk in edge_tts.Communicate(sentence, voice).stream():
                if chunk["type"] == "audio":
                    out.extend(chunk["data"])
            return bytes(out)

        return asyncio.run(_collect())

    def stream(self, text: str, *, language: str | None = None) -> Iterator[bytes]:
        """Yield one MP3 blob per sentence as it is rendered."""
        from .sentences import split_sentences

        voice = self._voice_for(language)
        for sentence in split_sentences(text):
            try:
                audio = self._synthesize_one(sentence, voice)
            except Exception:  # pragma: no cover - network/engine best-effort
                logger.warning("edge-tts synthesis failed for a sentence", exc_info=True)
                continue
            if audio:
                yield audio

    def synthesize(self, text: str, *, language: str | None = None) -> bytes:
        """Full reply as one MP3 (concatenated per-sentence frames)."""
        return b"".join(self.stream(text, language=language))
