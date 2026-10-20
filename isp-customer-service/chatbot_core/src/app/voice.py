"""Voice building blocks for the API — the ASR and TTS a call uses, the scripted lines
rendered ahead, and where a call's audio is recorded.

The call itself runs in `pipecat_call.py` (WebRTC, Smart Turn, interruptions); this module
builds its parts once per process (env knobs: ASR_BACKEND, GROQ_MODEL, TTS_ENGINE,
TTS_PIPER_VOICE…) and is rebuilt when the config page changes a voice key.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

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
    engine = os.environ.get("TTS_ENGINE", "piper").lower()
    if engine == "gtts":
        from adapters.tts import GTTSProvider

        logger.info("voice tts: gtts")
        return GTTSProvider(default_language=_LANGUAGE)
    if engine == "piper":
        # Local Lithuanian voice (MODELIAI.md S2, 2026-10-05: be independent of the
        # unofficial edge endpoint). Not downloaded or no `piper-tts` -> edge-tts.
        from adapters.tts import PiperTTSProvider

        piper_voice = os.environ.get("TTS_PIPER_VOICE", "reginute").lower()
        try:
            provider = PiperTTSProvider(voice=piper_voice, default_language=_LANGUAGE)
            if os.environ.get("TTS_PIPER_PROCESS", "on").lower() != "off":
                # Rendering in worker processes, outside the server's GIL (piper_pool.py).
                try:
                    from adapters.tts.piper_pool import PooledPiperTTSProvider

                    provider = PooledPiperTTSProvider(voice=piper_voice, default_language=_LANGUAGE)
                except Exception as exc:  # the voice still works in-process
                    logger.warning(f"voice tts: piper pool failed ({exc}); rendering in-process")
            import lameenc  # noqa: F401 - fail here, not mid-call
            import piper  # noqa: F401

            logger.info(f"voice tts: piper {piper_voice} (local)")
            return provider
        except (ImportError, FileNotFoundError, ValueError) as exc:
            logger.warning(f"voice tts: piper unavailable ({exc}); falling back to edge-tts")
    from adapters.tts import EdgeTTSProvider

    voice = os.environ.get("TTS_VOICE", "lt-LT-LeonasNeural")
    logger.info(f"voice tts: edge {voice}")
    return EdgeTTSProvider(default_language=_LANGUAGE, voice=voice)


def close_tts() -> None:
    """Stop the current TTS's worker processes (a Piper pool) before it is rebuilt."""
    if _build_tts.cache_info().currsize:
        close = getattr(_build_tts(), "close", None)
        if callable(close):
            close()


# The locale groups whose lines the engine SPEAKS as scripted replies (the rest —
# detector glosses, verdict glosses, pack meanings — only feed the LLM).
PREWARM_GROUPS = ("system", "identification", "ticket", "inform", "faq", "solver", "problem")


def scripted_lines() -> list[str]:
    """Every fixed line the engine may speak word for word: the opening line and the
    scripted phrases without placeholders."""
    from agent.config import create_config
    from agent.contract.locale import current, phrase

    lines = [phrase("system.greeting", company_name=create_config().company_name)]
    for key, text in current().phrases.items():
        if key.split(".", 1)[0] in PREWARM_GROUPS and "{" not in text:
            lines.append(text)
    return lines


def prewarm_tts() -> int:
    """Render the scripted lines into the TTS cache (review finding AL) — run once in
    a background thread at startup, so a mechanical turn never waits on the network.
    TTS_PREWARM=off skips it."""
    if os.environ.get("TTS_PREWARM", "on").lower() == "off":
        return 0
    from agent.voice_pipeline import prewarm

    rendered = prewarm(_build_tts(), scripted_lines(), language=_LANGUAGE, pause_s=0.2)
    logger.info(f"tts prewarm: {rendered} new pieces rendered")
    return rendered


def _record_dir(session_id: str) -> Path:
    base = os.environ.get("API_RECORD_DIR")
    root = Path(base) if base else Path(__file__).resolve().parents[3] / "logs" / "sessions"
    return root / session_id


def _manifest(d: Path, side: str, filename: str, **extra: Any) -> None:
    """Timeline entry for the replay bench (VOICE_PLAN: two-track recording
    with a timing manifest) — best-effort append to manifest.jsonl."""
    import json
    import time

    try:
        entry = {"t": round(time.time(), 3), "side": side, "file": filename, **extra}
        with open(d / "manifest.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # pragma: no cover - best-effort
        logger.debug("manifest append failed", exc_info=True)
