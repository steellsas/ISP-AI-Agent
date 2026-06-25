"""
VoicePipeline — framework-free glue: audio in -> AgentSession -> audio out.

This is the reusable heart of the voice slice. It composes three swappable
pieces and nothing else:

    ASRProvider  (speech -> text)
    AgentSession (text turn -> text reply)   # the stable seam from Phase 2
    TTSProvider  (text -> speech)

It knows nothing about WebRTC, sockets, Streamlit or FastRTC — a Transport
(Phase 3 next step) owns the wire and simply calls `greeting_audio()` once and
`handle_audio()` per caller utterance. Keeping this transport-agnostic means the
exact same pipeline serves a FastRTC web demo today and Twilio/PBX telephony
later, with no change here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .session import AgentSession

if TYPE_CHECKING:
    from src.ports.asr import ASRProvider
    from src.ports.tts import TTSProvider


@dataclass
class VoiceTurn:
    """One processed utterance: what was heard, what was said, and its audio."""

    transcript: str  # ASR text of the caller's utterance
    reply_text: str  # the agent's text reply
    reply_audio: bytes  # synthesized speech for `reply_text`
    is_complete: bool  # whether the conversation has ended
    # Per-stage wall-clock latency (ms). The honest "how long did the caller
    # wait" breakdown — the raw material for the latency-masking decision.
    asr_ms: float = 0.0  # speech -> text
    agent_ms: float = 0.0  # text turn -> reply (LLM + tools)
    tts_ms: float = 0.0  # text -> speech


class VoicePipeline:
    """Compose ASR + AgentSession + TTS into one audio-in/audio-out turn loop."""

    def __init__(
        self,
        session: AgentSession,
        asr: ASRProvider,
        tts: TTSProvider,
        *,
        language: str | None = None,
        transcript_filter: Callable[[str], str] | None = None,
        noise_filter: Callable[[str], bool] | None = None,
    ):
        """
        Args:
            session: The conversation seam (one per call).
            asr: Speech-to-text backend (any `ASRProvider`).
            tts: Text-to-speech backend (any `TTSProvider`).
            language: ISO hint passed to ASR/TTS; defaults to the session's
                configured language.
            transcript_filter: optional post-ASR text cleanup applied to the
                transcript before the agent sees it (e.g. spoken-number ->
                digit normalization for voice). Keeps the pipeline generic —
                the language-specific logic lives in an adapter.
            noise_filter: optional predicate; when it returns True for a
                transcript (silence/noise hallucination), the turn is DROPPED —
                the agent is not called and no reply is spoken, so it stays
                silent and waits for real speech instead of answering noise.
        """
        self._session = session
        self._asr = asr
        self._tts = tts
        self._language = language or session.config.language
        self._filler_audio: bytes | None = None  # lazily synthesized cue (2.2)
        self._transcript_filter = transcript_filter
        self._noise_filter = noise_filter

    @property
    def session(self) -> AgentSession:
        """The underlying conversation (read-only access to state/stats)."""
        return self._session

    def greeting_audio(self) -> bytes:
        """Synthesize the opening line spoken before the caller says anything."""
        greeting = self._session.greeting()
        return self._tts.synthesize(greeting, language=self._language)

    # A short "thinking" cue the transport plays immediately while the real reply
    # (ASR + agent + TTS) is still computing — masks per-turn latency (step 2.2).
    # Synthesized once and cached (it never changes); the general static-phrase
    # audio cache is step 2.3.
    _FILLER_TEXT = {"lt": "Sekundėlę, tikrinu.", "en": "One moment, let me check."}

    def filler_audio(self) -> bytes:
        """Cached audio for the short 'let me check' cue (lazily synthesized)."""
        if self._filler_audio is None:
            text = self._FILLER_TEXT.get(self._language, self._FILLER_TEXT["lt"])
            self._filler_audio = self._tts.synthesize(text, language=self._language)
        return self._filler_audio

    def handle_audio(self, audio: bytes, *, sample_rate: int = 16_000) -> VoiceTurn:
        """
        Run one full voice turn: transcribe -> agent reply -> synthesize.

        Args:
            audio: Caller utterance (WAV or raw 16-bit PCM).
            sample_rate: Sample rate for raw PCM (ignored for WAV).

        Returns:
            A `VoiceTurn` with transcript, reply text, reply audio and the
            conversation-complete flag.
        """
        t0 = time.perf_counter()
        raw_transcript = self._asr.transcribe(
            audio, language=self._language, sample_rate=sample_rate
        )
        transcript = raw_transcript
        if self._transcript_filter and transcript:
            transcript = self._transcript_filter(transcript)
        t1 = time.perf_counter()

        tracer = getattr(self._session, "tracer", None)

        # Drop silence/noise hallucinations: ignore the turn, stay silent, wait
        # for real speech (answering "www.youtube.come" breaks the conversation).
        dropped = bool(self._noise_filter and self._noise_filter(transcript))
        if tracer is not None:
            # The STT record: RAW vs after normalization, + whether it was dropped.
            tracer.emit(
                "asr",
                raw=raw_transcript,
                transcript=transcript,
                ms=round((t1 - t0) * 1000.0),
                dropped=dropped,
            )
        if dropped:
            return VoiceTurn(
                transcript=transcript,
                reply_text="",
                reply_audio=b"",
                is_complete=self._session.is_complete,
                asr_ms=(t1 - t0) * 1000.0,
            )

        reply_text = self._session.handle_turn(transcript)
        t2 = time.perf_counter()
        reply_audio = self._tts.synthesize(reply_text, language=self._language)
        t3 = time.perf_counter()

        asr_ms = (t1 - t0) * 1000.0
        agent_ms = (t2 - t1) * 1000.0
        tts_ms = (t3 - t2) * 1000.0

        # Surface the latency breakdown into the conversation trace so it is
        # measurable per turn from the JSONL (where the 10 s actually goes).
        if tracer is not None:
            tracer.emit(
                "voice_latency",
                asr_ms=round(asr_ms),
                agent_ms=round(agent_ms),
                tts_ms=round(tts_ms),
                total_ms=round(asr_ms + agent_ms + tts_ms),
            )

        return VoiceTurn(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=reply_audio,
            is_complete=self._session.is_complete,
            asr_ms=asr_ms,
            agent_ms=agent_ms,
            tts_ms=tts_ms,
        )

    def stream_turn(self, audio: bytes, *, sample_rate: int = 16_000) -> Iterator[bytes]:
        """
        Run one turn and STREAM the reply audio in chunks (one per sentence) so the
        transport can start playing before the whole reply is rendered (Pillar C2b).

        Same ASR + noise-drop + agent path as handle_audio; emits the same
        `asr` / `voice_latency` trace events (tts_ms here = time-to-first-audio,
        the metric that matters for streaming). Falls back to a single
        synthesize() blob if the TTS cannot stream. A noise turn yields nothing.
        """
        t0 = time.perf_counter()
        raw_transcript = self._asr.transcribe(
            audio, language=self._language, sample_rate=sample_rate
        )
        transcript = raw_transcript
        if self._transcript_filter and transcript:
            transcript = self._transcript_filter(transcript)
        t1 = time.perf_counter()

        tracer = getattr(self._session, "tracer", None)
        dropped = bool(self._noise_filter and self._noise_filter(transcript))
        if tracer is not None:
            tracer.emit(
                "asr",
                raw=raw_transcript,
                transcript=transcript,
                ms=round((t1 - t0) * 1000.0),
                dropped=dropped,
            )
        if dropped:
            return

        reply_text = self._session.handle_turn(transcript)
        t2 = time.perf_counter()
        asr_ms = (t1 - t0) * 1000.0
        agent_ms = (t2 - t1) * 1000.0

        stream = getattr(self._tts, "stream", None)
        if callable(stream):
            chunks = stream(reply_text, language=self._language)
        else:  # non-streaming TTS -> a single blob
            chunks = iter([self._tts.synthesize(reply_text, language=self._language)])

        emitted = False
        for chunk in chunks:
            if not chunk:
                continue
            if not emitted:
                if tracer is not None:
                    ttfa = (time.perf_counter() - t2) * 1000.0  # time to first audio
                    tracer.emit(
                        "voice_latency",
                        asr_ms=round(asr_ms),
                        agent_ms=round(agent_ms),
                        tts_ms=round(ttfa),
                        total_ms=round(asr_ms + agent_ms + ttfa),
                    )
                emitted = True
            yield chunk

        if not emitted and tracer is not None:  # empty reply
            tracer.emit(
                "voice_latency",
                asr_ms=round(asr_ms),
                agent_ms=round(agent_ms),
                tts_ms=0,
                total_ms=round(asr_ms + agent_ms),
            )
