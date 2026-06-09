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

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .session import AgentSession

if TYPE_CHECKING:
    from src.ports.asr import ASRProvider
    from src.ports.tts import TTSProvider

# Per-turn transcript + timing go to the file-only "transcript" logger (set up
# by utils.setup_session_logging), so a voice session is reviewable exactly like
# a text CLI one. When no transcript handler is configured (e.g. unit tests),
# these records are silently dropped — pure instrumentation, no behaviour change.
_transcript = logging.getLogger("transcript")


@dataclass
class VoiceTurn:
    """One processed utterance: what was heard, what was said, and its audio."""

    transcript: str  # ASR text of the caller's utterance
    reply_text: str  # the agent's text reply
    reply_audio: bytes  # synthesized speech for `reply_text`
    is_complete: bool  # whether the conversation has ended


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
        t0 = time.perf_counter()
        greeting = self._session.greeting()
        t1 = time.perf_counter()
        audio = self._tts.synthesize(greeting, language=self._language)
        t2 = time.perf_counter()
        _transcript.info("GREETING (agent %.1fs | tts %.1fs): %s", t1 - t0, t2 - t1, greeting)
        return audio

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
        # Same transcript shape as the text CLI, plus the voice latency breakdown
        # (ASR vs agent vs TTS) so slow turns can be pinned to the right stage.
        _transcript.info("USER: %s", transcript)
        _transcript.info(
            "AGENT (asr %.1fs | agent %.1fs | tts %.1fs | total %.1fs): %s",
            t1 - t0,
            t2 - t1,
            t3 - t2,
            t3 - t0,
            reply_text,
        )
        return VoiceTurn(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=reply_audio,
            is_complete=self._session.is_complete,
        )
