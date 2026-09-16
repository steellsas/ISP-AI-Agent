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
import os
import re
from collections.abc import Iterator

logger = logging.getLogger(__name__)

# Default voices per language (extend as more locales are added). Lithuanian
# defaults to the male voice — fits the support-specialist persona.
_VOICES = {"lt": "lt-LT-LeonasNeural", "en": "en-US-GuyNeural"}


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

    @staticmethod
    def _pct(env_key: str) -> str | None:
        """A validated '+N%'/'-N%' knob from the env; None = engine default."""
        raw = (os.getenv(env_key) or "").strip()
        if not raw or raw in ("+0%", "0%", "0"):
            return None
        return raw if re.fullmatch(r"[+-]\d{1,2}%", raw) else None

    # S3 (2026-08-24): repeated sentences (greeting, wait_ack, ticket
    # questions, goodbyes) synthesize once per (text, voice, rate, pitch) —
    # a small capped cache, ~20 KB per entry.
    _CACHE: dict[tuple, bytes] = {}
    _CACHE_MAX = 64
    # How long one sentence's synthesis may take before the socket is abandoned.
    last_synthesis_ms: int = 0

    def _synthesize_one(self, sentence: str, voice: str) -> bytes:
        """Render one sentence to MP3 via edge-tts (async collected to bytes).
        TTS_RATE speeds the delivery (like video 1.1x); TTS_PITCH shifts the
        voice — lower ('-5%') sounds more matter-of-fact/technical (Andrius
        2026-08-20). Both from the config page, validated, engine default when
        unset."""
        kwargs = {}
        rate = self._pct("TTS_RATE")
        if rate:
            kwargs["rate"] = rate
        pitch = (os.getenv("TTS_PITCH") or "").strip()
        if pitch and pitch not in ("+0Hz", "0Hz", "0") and re.fullmatch(r"[+-]\d{1,3}Hz", pitch):
            kwargs["pitch"] = pitch

        cache_key = (sentence, voice, kwargs.get("rate"), kwargs.get("pitch"))
        cached = self._CACHE.get(cache_key)
        if cached is not None:
            logger.debug("edge-tts cache hit (%d chars)", len(sentence))
            return cached

        import time

        import edge_tts  # deferred (optional dependency) — a cache hit needs none

        async def _collect(deadline: float) -> bytes:
            """Collect one sentence's audio. The DEADLINE guards the FIRST chunk only:
            a stalled socket answers nothing at all, while a long sentence keeps
            streaming once it has started."""
            out = bytearray()
            stream = edge_tts.Communicate(sentence, voice, **kwargs).stream()
            first = True
            while True:
                try:
                    chunk = (
                        await asyncio.wait_for(anext(stream), timeout=deadline)
                        if first
                        else await anext(stream)
                    )
                except StopAsyncIteration:
                    break
                first = False
                if chunk["type"] == "audio":
                    out.extend(chunk["data"])
            return bytes(out)

        # Latency observability (2026-09-11): each sentence is a separate
        # websocket round-trip to the free Microsoft endpoint, and intermittent
        # throttling shows up as multi-second stalls mid-reply. Log every
        # synthesis; a slow one is a WARNING so the stall is visible in the
        # server log without debug level.
        # A stalled socket is abandoned rather than waited out: the free endpoint
        # regularly answers nothing for 6-30 s (measured 2026-09-16) while the caller
        # hears silence. A fresh connection usually answers at once, so we keep
        # reconnecting inside a budget instead of waiting on one dead socket.
        deadline, budget = _stall_deadline(), _total_budget()
        t0 = time.perf_counter()
        audio = b""
        attempt = 0
        while time.perf_counter() - t0 < budget:
            attempt += 1
            try:
                audio = asyncio.run(_collect(deadline))
                break
            except TimeoutError:
                logger.warning(
                    "edge-tts sent no audio within %.1fs (attempt %d, %d chars)",
                    deadline,
                    attempt,
                    len(sentence),
                )
            except Exception:  # pragma: no cover - transport hiccup, try again
                logger.warning("edge-tts attempt %d failed (%d chars)", attempt, len(sentence))
        ms = int((time.perf_counter() - t0) * 1000)
        log = logger.warning if ms > 3000 else logger.info
        log("edge-tts: %d chars -> %d bytes in %d ms", len(sentence), len(audio), ms)
        self.last_synthesis_ms = ms
        if audio:
            if len(self._CACHE) >= self._CACHE_MAX:
                self._CACHE.pop(next(iter(self._CACHE)))
            self._CACHE[cache_key] = audio
        return audio

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


def _total_budget() -> float:
    """Seconds the whole sentence may spend across reconnects before we give up and the
    caller loses that sentence (knowledge/limits.yaml `tts_budget_seconds`)."""
    from agent.contract import limits

    try:
        return float(limits.get("tts_budget_seconds"))
    except Exception:  # pragma: no cover - the adapter must work without the engine
        return 10.0


def _stall_deadline() -> float:
    """Seconds to wait for the FIRST audio chunk (knowledge/limits.yaml
    `tts_stall_seconds`); after that the socket is abandoned and retried once."""
    from agent.contract import limits

    try:
        return float(limits.get("tts_stall_seconds"))
    except Exception:  # pragma: no cover - the adapter must work without the engine
        return 4.0
