"""How a reply becomes speech — the text a TTS is given, in the active language's spoken form.

The call's audio runs in `app/pipecat_call.py` (Pipecat); these helpers are shared by it and by
the startup prewarm of the scripted lines, so a cached line and a live one are the same text.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def spoken_sentences(text: str) -> list[str]:
    """The pieces a reply text is synthesized in: sentences as they complete, then the
    tail — in their spoken (TTS) form."""
    from src.adapters.tts.sentences import pop_sentence

    pieces: list[str] = []
    sentence, buf = pop_sentence(text)
    while sentence:
        pieces.append(sentence)
        sentence, buf = pop_sentence(buf)
    if buf.strip():
        pieces.append(buf.strip())
    return [speech_text(p) for p in pieces]


def prewarm(tts, texts: list[str], *, language: str, pause_s: float = 0.0) -> int:
    """Render the given lines ahead of any call (review finding AL): a scripted turn
    then plays from the TTS cache. Returns how many pieces were newly synthesized.
    Best-effort — a failure skips that piece."""
    is_cached = getattr(tts, "is_cached", None)
    rendered = 0
    for text in texts:
        for piece in spoken_sentences(text):
            if callable(is_cached) and is_cached(piece, language=language):
                continue
            try:
                tts.synthesize(piece, language=language)
                rendered += 1
            except Exception:  # pragma: no cover - best-effort
                logger.debug("prewarm synthesis failed", exc_info=True)
            if pause_s:
                time.sleep(pause_s)
    return rendered


def speech_text(text: str) -> str:
    """The text sent to TTS in the spoken form of the active language (e.g.
    street abbreviations read out). Traces and the UI keep the canonical form."""
    from .contract.locale import lang

    return lang().speech_text(text)
