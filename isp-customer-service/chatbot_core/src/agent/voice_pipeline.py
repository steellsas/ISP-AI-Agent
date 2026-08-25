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

import io
import os
import re
import time
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .session import AgentSession

if TYPE_CHECKING:
    from src.ports.asr import ASRProvider
    from src.ports.tts import TTSProvider


# "Tilžės g. 60-7" is written form — TTS reads it "g. šešiasdešimt minus septyni".
# Speak addresses like a human: "Tilžės gatvė, namas 60, butas 7". Applied ONLY to
# the text sent to TTS; the reply text (traces, UI) keeps the canonical form.
_ADDR_HOUSE_FLAT = re.compile(r"\bg\.\s*(\d+)\s*-\s*(\d+)\b")
_ADDR_HOUSE = re.compile(r"\bg\.(?=\s*\d)")
_ADDR_ABBR = re.compile(r"\bg\.(?=\s|$)")


def audio_duration_s(audio: bytes, sample_rate: int = 16_000) -> float | None:
    """Best-effort duration of a WAV container or raw 16-bit mono PCM. None
    when it cannot be read — the caller then skips the too-short guard."""
    if not audio:
        return 0.0
    try:
        if audio[:4] == b"RIFF":
            with wave.open(io.BytesIO(audio), "rb") as w:
                rate = w.getframerate() or sample_rate
                return w.getnframes() / float(rate)
        return len(audio) / (2.0 * float(sample_rate))
    except Exception:  # pragma: no cover - guard must never break the turn
        return None


def _min_audio_s() -> float:
    """Too-short-audio floor (VOICE_PLAN V1): fragments under this are DROPPED
    before ASR — Whisper hallucinates words from sub-word blips ("Įvėtojai")."""
    try:
        return float(os.getenv("ASR_MIN_AUDIO_S", "0.3"))
    except ValueError:
        return 0.3


def normalize_lt_address_speech(text: str) -> str:
    """Spoken form for LT street addresses: 'X g. 60-7' -> 'X gatvė, namas 60, butas 7',
    'X g. 60' -> 'X gatvė 60', a dangling 'g.' -> 'gatvė'."""
    if not text or "g." not in text:
        return text
    out = _ADDR_HOUSE_FLAT.sub(r"gatvė, namas \1, butas \2", text)
    out = _ADDR_HOUSE.sub("gatvė", out)
    return _ADDR_ABBR.sub("gatvė", out)


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

    def _asr_context(self) -> str | None:
        """Per-turn STT biasing from the session (VOICE_PLAN V1); best-effort."""
        provider = getattr(self._session, "asr_context", None)
        if not callable(provider):
            return None
        try:
            return provider()
        except Exception:  # pragma: no cover - biasing must never break a turn
            return None

    def _transcribe(self, audio: bytes, sample_rate: int, context: str | None) -> str:
        """Call the ASR with the dialogue context; adapters/stubs without the
        `context` parameter keep working (TypeError -> plain call)."""
        try:
            return self._asr.transcribe(
                audio, language=self._language, sample_rate=sample_rate, context=context
            )
        except TypeError:
            return self._asr.transcribe(audio, language=self._language, sample_rate=sample_rate)

    def _tts_stream(self, text: str):
        """Per-sentence TTS for a ready reply text (stream() when available)."""
        stream = getattr(self._tts, "stream", None)
        chunks = (
            stream(normalize_lt_address_speech(text), language=self._language)
            if callable(stream)
            else iter(
                [self._tts.synthesize(normalize_lt_address_speech(text), language=self._language)]
            )
        )
        for chunk in chunks:
            if chunk:
                yield chunk

    def _too_short(self, audio: bytes, sample_rate: int, tracer) -> bool:
        """Too-short-audio guard (VOICE_PLAN V1): sub-word blips are dropped
        BEFORE ASR — Whisper hallucinates words from them. Traced as a dropped
        asr event so replay/tuning sees every skipped fragment."""
        dur = audio_duration_s(audio, sample_rate)
        if dur is None or dur >= _min_audio_s():
            return False
        if tracer is not None:
            tracer.emit(
                "asr",
                raw="",
                transcript="",
                ms=0,
                dropped=True,
                reason="too_short",
                dur_s=round(dur, 2),
            )
        return True

    def transcribe_partial(self, audio: bytes, *, sample_rate: int = 16_000) -> str:
        """E1 duplex: transcribe a GROWING utterance snapshot (the caller is
        still speaking). Same ASR + dialogue context + LT normalization as the
        turn path, but NO agent turn, NO state — the caller reads the result
        from the trace. Partials are inherently jittery (Whisper changes its
        mind on a growing window); consumers must treat them as hints only."""
        context = self._asr_context()
        text = self._transcribe(audio, sample_rate, context)
        if self._transcript_filter and text:
            text = self._transcript_filter(text)
        # Same noise gate as the turn path: a snapshot mid-word makes Whisper
        # hallucinate ("www.youtube.come" observed on the very first probe) —
        # an empty partial reads better than junk.
        if text and self._noise_filter and self._noise_filter(text):
            return ""
        return text or ""

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
        tracer = getattr(self._session, "tracer", None)
        if self._too_short(audio, sample_rate, tracer):
            return VoiceTurn(
                transcript="",
                reply_text="",
                reply_audio=b"",
                is_complete=self._session.is_complete,
            )
        t0 = time.perf_counter()
        context = self._asr_context()
        raw_transcript = self._transcribe(audio, sample_rate, context)
        transcript = raw_transcript
        if self._transcript_filter and transcript:
            transcript = self._transcript_filter(transcript)
        t1 = time.perf_counter()

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
                context=(context or "")[:160],
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
        reply_audio = self._tts.synthesize(
            normalize_lt_address_speech(reply_text), language=self._language
        )
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

    def stream_turn(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16_000,
        should_stop: Callable[[], bool] | None = None,
        interruption: Callable[[str], str | None] | None = None,
    ) -> Iterator[bytes]:
        """
        Run one turn and STREAM the reply audio in chunks (one per sentence) so the
        transport can start playing before the whole reply is rendered (Pillar C2b).

        Same ASR + noise-drop + agent path as handle_audio; emits the same
        `asr` / `voice_latency` trace events (tts_ms here = time-to-first-audio,
        the metric that matters for streaming). Falls back to a single
        synthesize() blob if the TTS cannot stream. A noise turn yields nothing.

        `should_stop` (Phase 5 PR3, barge-in): checked between sentences — when
        it turns True the agent token stream is CLOSED (the LLM generation stops
        with it), and the session's on_turn_cancelled hook gets the text that was
        actually synthesized, so the engine rolls its ask-bookkeeping back.
        """
        tracer = getattr(self._session, "tracer", None)
        # D1 delivery ledger: the sentence behind EVERY yielded chunk, in send
        # order — after a barge-in the transport truncates the engine's history
        # to what the caller actually HEARD. `aligned` goes False whenever a
        # chunk without a matching sentence goes out (filler, error fallback,
        # whole-reply TTS split) — then the ledger is unusable and delivery
        # falls back to today's assume-all-heard behaviour.
        self.last_turn_sentences: list[str] = []
        self.last_turn_aligned = True
        if self._too_short(audio, sample_rate, tracer):
            return
        t0 = time.perf_counter()
        context = self._asr_context()
        raw_transcript = self._transcribe(audio, sample_rate, context)
        transcript = raw_transcript
        if self._transcript_filter and transcript:
            transcript = self._transcript_filter(transcript)
        t1 = time.perf_counter()

        dropped = bool(self._noise_filter and self._noise_filter(transcript))
        if tracer is not None:
            tracer.emit(
                "asr",
                raw=raw_transcript,
                transcript=transcript,
                ms=round((t1 - t0) * 1000.0),
                dropped=dropped,
                context=(context or "")[:160],
            )
        if dropped:
            return

        # Smart barge-in (L3a): the previous turn was cut by this utterance —
        # a bare backchannel ("taip", "mhm") or our own speakerphone echo must
        # NOT become a dialogue turn. Re-anchor the standing question instead;
        # "stop"/"substantive" fall through to normal processing (default-deny).
        verdict = interruption(transcript) if interruption is not None else None
        if verdict is not None and tracer is not None:
            tracer.emit("barge_in", verdict=verdict, transcript=transcript[:120])
        if verdict in ("consent", "echo"):
            anchor = getattr(self._session, "anchor_text", None)
            text = anchor() if callable(anchor) else ""
            if text:
                chunk = self._tts.synthesize(
                    normalize_lt_address_speech(text), language=self._language
                )
                if chunk:
                    self.last_turn_sentences.append(text)
                    yield chunk
            return

        asr_ms = (t1 - t0) * 1000.0
        emitted = False

        def _emit_latency(audio_ready_at: float) -> None:
            nonlocal emitted
            if not emitted and tracer is not None:
                # With token streaming the agent + TTS overlap, so report the one
                # number that matters: ASR-done -> first audio (when speech starts).
                to_first = (audio_ready_at - t1) * 1000.0
                tracer.emit(
                    "voice_latency",
                    asr_ms=round(asr_ms),
                    agent_ms=0,
                    tts_ms=round(to_first),
                    total_ms=round(asr_ms + to_first),
                )
            emitted = True

        # S1 speculation (2026-08-24): if this utterance maps to a PREPARED
        # branch, the engine turn still runs (all bookkeeping intact) but its
        # reply is the injected precomputed text — and the audio comes from
        # the cache. Mismatch anywhere -> the injection is ignored and the
        # normal LLM+TTS path below runs untouched.
        matcher = getattr(self._session, "speculation_match", None)
        spec_audio = matcher(transcript) if callable(matcher) else None
        if spec_audio:
            gen = getattr(self._session, "handle_turn_stream", None)
            reply = (
                "".join(gen(transcript)) if callable(gen) else self._session.handle_turn(transcript)
            )
            if reply and reply == getattr(self._session, "_last_injected_text", None):
                _emit_latency(time.perf_counter())
                self.last_turn_sentences.append(reply)
                yield spec_audio
                return
            if reply:  # the engine chose its own reply — synthesize it normally
                self.last_turn_aligned = False  # tts.stream splits opaquely
                for sentence_audio in self._tts_stream(reply):
                    _emit_latency(time.perf_counter())
                    yield sentence_audio
                return

        # Pillar C3: if the session streams the reply token by token, buffer to
        # sentence boundaries and synthesize each sentence as soon as it completes.
        agent_stream = getattr(self._session, "handle_turn_stream", None)
        if callable(agent_stream):
            from src.adapters.tts.sentences import pop_sentence

            # On cancel the ENGINE does its own bookkeeping (the same flag stops
            # its token loop — see ReactAgent.request_cancel); here we only stop
            # SYNTHESIZING, so no half-sentence audio goes out after the barge-in.
            buf = ""
            gen = agent_stream(transcript)
            for token in gen:
                if should_stop is not None and should_stop():
                    return
                buf += token
                sentence, buf = pop_sentence(buf)
                while sentence:
                    if should_stop is not None and should_stop():
                        return
                    chunk = self._tts.synthesize(
                        normalize_lt_address_speech(sentence), language=self._language
                    )
                    if chunk:
                        _emit_latency(time.perf_counter())
                        self.last_turn_sentences.append(sentence)
                        yield chunk
                    sentence, buf = pop_sentence(buf)
            tail = buf.strip()
            if tail:
                chunk = self._tts.synthesize(
                    normalize_lt_address_speech(tail), language=self._language
                )
                if chunk:
                    _emit_latency(time.perf_counter())
                    self.last_turn_sentences.append(tail)
                    yield chunk
            if not emitted and tracer is not None:
                tracer.emit(
                    "voice_latency",
                    asr_ms=round(asr_ms),
                    agent_ms=0,
                    tts_ms=0,
                    total_ms=round(asr_ms),
                )
            return

        # Fallback (C2b): non-streaming agent -> full reply -> per-sentence TTS.
        self.last_turn_aligned = False  # chunk<->sentence mapping unknown here
        reply_text = self._session.handle_turn(transcript)
        stream = getattr(self._tts, "stream", None)
        if callable(stream):
            chunks = stream(normalize_lt_address_speech(reply_text), language=self._language)
        else:
            chunks = iter(
                [
                    self._tts.synthesize(
                        normalize_lt_address_speech(reply_text), language=self._language
                    )
                ]
            )
        for chunk in chunks:
            if not chunk:
                continue
            _emit_latency(time.perf_counter())
            yield chunk
        if not emitted and tracer is not None:
            tracer.emit(
                "voice_latency", asr_ms=round(asr_ms), agent_ms=0, tts_ms=0, total_ms=round(asr_ms)
            )
