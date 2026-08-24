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


def duplex_enabled() -> bool:
    """E1 duplex master switch (config page); off = today's behaviour untouched."""
    return os.environ.get("DUPLEX", "off").lower() == "on"


def run_voice_partial(ms: ManagedSession, audio: bytes) -> dict[str, Any] | None:
    """E1 duplex: rolling PARTIAL transcript of the utterance-so-far. Trace +
    client display only — never an agent turn, never state. The result is also
    kept on the session (ms.last_partial) for the E2 endpointer."""
    import time

    if not duplex_enabled():
        return None
    pipeline = get_pipeline(ms)
    t0 = time.perf_counter()
    try:
        text = pipeline.transcribe_partial(audio)
    except Exception:  # a failed partial must never disturb the call
        logger.debug("partial asr failed", exc_info=True)
        return None
    took = round((time.perf_counter() - t0) * 1000)
    ms.last_partial = text
    # E2: the semantic endpoint hint rides along — the client adjusts how much
    # trailing silence to require before cutting the turn.
    mode, silence_ms = "normal", None
    hint = getattr(ms.session, "endpoint_hint", None)
    if callable(hint):
        mode, silence_ms = hint(text)
    ms.session.tracer.emit("partial", text=text, ms=took, audio_bytes=len(audio), endpoint=mode)
    return {"type": "partial", "text": text, "ms": took, "endpoint": mode, "silence_ms": silence_ms}


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
    # Smart barge-in (L3a): when THIS utterance is the one that cut the agent
    # off mid-reply, classify it — a bare backchannel/echo re-anchors the
    # standing question instead of derailing the dialogue (default-deny:
    # anything unclear processes normally).
    interruption = None
    if bool(getattr(pipeline, "prev_cancelled", False)):

        def interruption(transcript: str) -> str | None:
            from agent.barge_in import classify_interruption

            return classify_interruption(transcript, ms.session.last_spoken_text())

    # Filler (live 2026-08-14: "spragos tarp klausimų" — tts_first 5–10 s is
    # the LLM thinking): if no real audio is ready within VOICE_FILLER_AFTER_S,
    # speak the cached "Sekundėlę, tikrinu." cue. The delay keeps it away from
    # dropped noise/backchannel turns (they finish silently well under it).
    import threading

    got_audio = threading.Event()

    def _maybe_filler() -> None:
        if got_audio.is_set() or ms.cancel.is_set():
            return
        try:
            fa = pipeline.filler_audio()
            if fa and not got_audio.is_set():
                on_chunk(bytes(fa))
        except Exception:  # pragma: no cover - the cue must never break a turn
            logger.debug("filler failed", exc_info=True)

    filler_timer = None
    # Default OFF (Andrius 2026-08-20: the canned cue reads as junk — natural
    # LLM speech only; the knob stays for experiments).
    if os.environ.get("VOICE_FILLER", "off").lower() == "on":
        try:
            delay = float(os.environ.get("VOICE_FILLER_AFTER_S", "1.2"))
        except ValueError:
            delay = 1.2
        filler_timer = threading.Timer(delay, _maybe_filler)
        filler_timer.daemon = True
        filler_timer.start()

    # PR3: the barge-in cancel reaches the ENGINE — checked between sentences;
    # the token stream closes (LLM generation stops) and the ask-bookkeeping
    # rolls back via the session hook.
    turn_error = False
    try:
        for chunk in pipeline.stream_turn(
            audio, should_stop=ms.cancel.is_set, interruption=interruption
        ):
            if not chunk:
                continue
            got_audio.set()
            if filler_timer is not None:
                filler_timer.cancel()
            if first_ms is None:
                first_ms = round((time.perf_counter() - t0) * 1000)
            chunks += 1
            reply_audio.extend(chunk)
            on_chunk(bytes(chunk))
    except Exception as e:
        # A failed graph turn must NOT be silence (live 2026-08-13: every turn
        # after a poisoned state died mute — the caller kept talking to nothing
        # and hung up). Trace the error and SPEAK a scripted fallback so the
        # caller knows to retry; the next utterance starts a fresh turn.
        turn_error = True
        logger.exception("voice turn failed — speaking fallback")
        try:
            ms.session.tracer.emit("error", where="voice_turn", detail=str(e)[:300])
            from agent.identification import phrase

            fallback = phrase("turn_error")
            fb_audio = synthesize_text(fallback) if fallback else b""
            if fb_audio:
                chunks += 1
                reply_audio.extend(fb_audio)
                on_chunk(bytes(fb_audio))
        except Exception:  # pragma: no cover - the fallback must never raise
            logger.exception("voice turn fallback failed")
    finally:
        got_audio.set()  # a silent (dropped) turn must not get a late filler
        if filler_timer is not None:
            filler_timer.cancel()
    payload = {
        "type": "voice_turn_done",
        "chunks": chunks,
        "ttfa_ms": first_ms,
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "is_complete": ms.session.is_complete,
        "cancelled": ms.cancel.is_set(),
        "dropped": chunks == 0 and not ms.session.is_complete and not ms.cancel.is_set(),
        "error": turn_error,
    }
    # S1+S2 speculation (2026-08-24): while the caller does the thing we just
    # asked, a background thread prepares the likely next replies (branch
    # cache: standalone LLM+TTS per candidate answer) and refreshes telemetry
    # READ-ONLY; both fold in at the next turn.
    if (
        os.environ.get("SPECULATION", "on").lower() == "on"
        and not payload.get("is_complete")
        and not ms.cancel.is_set()
        and not turn_error
    ):

        def _speculate() -> None:
            try:
                ms.session.speculate_next(synthesize_text)
                ms.session.speculate_background_diagnosis()
            except Exception:  # pragma: no cover - background best-effort
                logger.debug("speculation thread failed", exc_info=True)

        threading.Thread(target=_speculate, daemon=True).start()
    if os.environ.get("API_RECORD_AUDIO", "1") != "0":
        try:
            d = _record_dir(ms.session.session_id)
            d.mkdir(parents=True, exist_ok=True)
            stem = f"turn_{ms.turn_count + 1:02d}"
            (d / f"{stem}_user.wav").write_bytes(audio)
            _manifest(d, "caller", f"{stem}_user.wav")
            if reply_audio:
                (d / f"{stem}_agent.mp3").write_bytes(bytes(reply_audio))
                _manifest(d, "agent", f"{stem}_agent.mp3", cancelled=ms.cancel.is_set())
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"audio recording failed: {e}")
    return payload


def _manifest(d: Path, side: str, filename: str, **extra: Any) -> None:
    """Timeline entry for the replay bench (VOICE_PLAN: dviejų takelių įrašymas
    su laiko manifestu) — best-effort append to manifest.jsonl."""
    import json
    import time

    try:
        entry = {"t": round(time.time(), 3), "side": side, "file": filename, **extra}
        with open(d / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # pragma: no cover - best-effort
        logger.debug("manifest append failed", exc_info=True)


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
            _manifest(d, "caller", f"{stem}_user.wav")
            if turn.reply_audio:
                (d / f"{stem}_agent.mp3").write_bytes(turn.reply_audio)
                _manifest(d, "agent", f"{stem}_agent.mp3")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"audio recording failed: {e}")
    return payload, turn.reply_audio
