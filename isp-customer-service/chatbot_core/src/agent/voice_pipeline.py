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
    ):
        """
        Args:
            session: The conversation seam (one per call).
            asr: Speech-to-text backend (any `ASRProvider`).
            tts: Text-to-speech backend (any `TTSProvider`).
            language: ISO hint passed to ASR/TTS; defaults to the session's
                configured language.
        """
        self._session = session
        self._asr = asr
        self._tts = tts
        self._language = language or session.config.language

    @property
    def session(self) -> AgentSession:
        """The underlying conversation (read-only access to state/stats)."""
        return self._session

    def greeting_audio(self) -> bytes:
        """Synthesize the opening line spoken before the caller says anything."""
        greeting = self._session.greeting()
        return self._tts.synthesize(greeting, language=self._language)

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
        transcript = self._asr.transcribe(audio, language=self._language, sample_rate=sample_rate)
        t1 = time.perf_counter()
        reply_text = self._session.handle_turn(transcript)
        t2 = time.perf_counter()
        reply_audio = self._tts.synthesize(reply_text, language=self._language)
        t3 = time.perf_counter()
        return VoiceTurn(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=reply_audio,
            is_complete=self._session.is_complete,
            asr_ms=(t1 - t0) * 1000.0,
            agent_ms=(t2 - t1) * 1000.0,
            tts_ms=(t3 - t2) * 1000.0,
        )
