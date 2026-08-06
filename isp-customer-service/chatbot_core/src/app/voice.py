"""Voice channel for the API (Phase 4 PR2) — WS audio in/out over the same session.

Reuses the whole voice stack the FastRTC demo proved: ASR/TTS adapters (same
env knobs — ASR_BACKEND, GROQ_MODEL, TTS_ENGINE, TTS_VOICE…), VoicePipeline
(noise drop, LT number/address normalization, asr + voice_latency trace
events). This module only adds: lazy per-session pipeline attachment, per-call
audio recording (archive zone), and one audio-turn entry the WS handler calls.

Half-duplex by agreement: the browser sends ONE complete utterance (client-side
end-pointing) as a WAV blob; barge-in/AEC is Phase 5.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .sessions import ManagedSession

logger = logging.getLogger(__name__)

_LANGUAGE = "lt"


@functools.lru_cache(maxsize=1)
def _build_asr():
    """One ASR per process (local Whisper would reload a model per call otherwise)."""
    from adapters.asr import DOMAIN_PROMPT_LT, FasterWhisperASR, GroqWhisperASR

    prompt = DOMAIN_PROMPT_LT if os.environ.get("WHISPER_PROMPT", "1") != "0" else None
    if os.environ.get("ASR_BACKEND", "groq").lower() == "groq":
        model = os.environ.get("GROQ_MODEL", "whisper-large-v3")
        logger.info(f"voice asr: groq {model}")
        return GroqWhisperASR(model, default_language=_LANGUAGE, initial_prompt=prompt)
    size = os.environ.get("WHISPER_MODEL", "small")
    logger.info(f"voice asr: faster-whisper {size} (local)")
    return FasterWhisperASR(
        size,
        device="cpu",
        compute_type="int8",
        beam_size=int(os.environ.get("WHISPER_BEAM", "1")),
        initial_prompt=prompt,
        vad_filter=os.environ.get("WHISPER_VAD", "1") != "0",
    )


@functools.lru_cache(maxsize=1)
def _build_tts():
    if os.environ.get("TTS_ENGINE", "edge").lower() == "gtts":
        from adapters.tts import GTTSProvider

        logger.info("voice tts: gtts")
        return GTTSProvider(default_language=_LANGUAGE)
    from adapters.tts import EdgeTTSProvider

    voice = os.environ.get("TTS_VOICE", "lt-LT-LeonasNeural")
    logger.info(f"voice tts: edge {voice}")
    return EdgeTTSProvider(default_language=_LANGUAGE, voice=voice)


def _record_dir(session_id: str) -> Path:
    base = os.environ.get("API_RECORD_DIR")
    root = Path(base) if base else Path(__file__).resolve().parents[3] / "logs" / "sessions"
    return root / session_id


def get_pipeline(ms: ManagedSession):
    """Attach (once) and return the VoicePipeline for this session."""
    if ms.voice is None:
        from adapters.asr import is_asr_noise, normalize_lt_numbers
        from agent.voice_pipeline import VoicePipeline

        ms.voice = VoicePipeline(
            ms.session,
            _build_asr(),
            _build_tts(),
            language=_LANGUAGE,
            transcript_filter=normalize_lt_numbers,
            noise_filter=is_asr_noise,
        )
    return ms.voice


def synthesize_text(text: str) -> bytes:
    """Speak an arbitrary agent line (greeting) with the same TTS + LT address
    normalization the turn path uses."""
    from agent.voice_pipeline import normalize_lt_address_speech

    return _build_tts().synthesize(normalize_lt_address_speech(text), language=_LANGUAGE)


def run_voice_turn_stream(ms: ManagedSession, audio: bytes, on_chunk) -> dict[str, Any]:
    """Phase 5 PR1 — STREAMING voice turn: the reply's audio is delivered
    sentence-by-sentence via on_chunk(bytes) (called from this worker thread)
    the moment each sentence's TTS is done, so the agent starts SPEAKING after
    the first sentence instead of after the whole reply. Returns the done
    payload (TTFA = utterance received -> first audio chunk). Recording still
    captures the full reply (chunks concatenated)."""
    import time

    pipeline = get_pipeline(ms)
    t0 = time.perf_counter()
    first_ms: int | None = None
    reply_audio = bytearray()
    chunks = 0
    # PR3: the barge-in cancel reaches the ENGINE — checked between sentences;
    # the token stream closes (LLM generation stops) and the ask-bookkeeping
    # rolls back via the session hook.
    for chunk in pipeline.stream_turn(audio, should_stop=ms.cancel.is_set):
        if not chunk:
            continue
        if first_ms is None:
            first_ms = round((time.perf_counter() - t0) * 1000)
        chunks += 1
        reply_audio.extend(chunk)
        on_chunk(bytes(chunk))
    payload = {
        "type": "voice_turn_done",
        "chunks": chunks,
        "ttfa_ms": first_ms,
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "is_complete": ms.session.is_complete,
        "cancelled": ms.cancel.is_set(),
        "dropped": chunks == 0 and not ms.session.is_complete and not ms.cancel.is_set(),
    }
    if os.environ.get("API_RECORD_AUDIO", "1") != "0":
        try:
            d = _record_dir(ms.session.session_id)
            d.mkdir(parents=True, exist_ok=True)
            stem = f"turn_{ms.turn_count + 1:02d}"
            (d / f"{stem}_user.wav").write_bytes(audio)
            if reply_audio:
                (d / f"{stem}_agent.mp3").write_bytes(bytes(reply_audio))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"audio recording failed: {e}")
    return payload


def run_voice_turn(ms: ManagedSession, audio: bytes) -> tuple[dict[str, Any], bytes]:
    """One utterance -> (voice_turn payload, reply audio bytes). Sync — the WS
    handler runs it in a worker thread. Recording is best-effort: the call must
    survive a full disk / locked file."""
    pipeline = get_pipeline(ms)
    turn = pipeline.handle_audio(audio)
    payload = {
        "type": "voice_turn",
        "transcript": turn.transcript,
        "reply": turn.reply_text,
        "is_complete": turn.is_complete,
        "asr_ms": round(turn.asr_ms),
        "agent_ms": round(turn.agent_ms),
        "tts_ms": round(turn.tts_ms),
        "dropped": not turn.reply_text and not turn.is_complete,
    }
    if os.environ.get("API_RECORD_AUDIO", "1") != "0":
        try:
            d = _record_dir(ms.session.session_id)
            d.mkdir(parents=True, exist_ok=True)
            stem = f"turn_{ms.turn_count + 1:02d}"
            (d / f"{stem}_user.wav").write_bytes(audio)
            if turn.reply_audio:
                (d / f"{stem}_agent.mp3").write_bytes(turn.reply_audio)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"audio recording failed: {e}")
    return payload, turn.reply_audio
