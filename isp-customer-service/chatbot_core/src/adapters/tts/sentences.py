"""Sentence splitting for streaming TTS — turn a reply into speakable chunks.

Streaming adapters synthesize and play one sentence at a time so the caller hears
the start of the reply before the whole thing is rendered (Pillar C). Kept tiny
and shared so gTTS and edge-tts chunk identically.
"""

from __future__ import annotations

import re

# Split AFTER sentence-final punctuation (keeping it) and on line breaks.
_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    """['Sveiki.', 'Ar veikia?'] from 'Sveiki. Ar veikia?' — empty in, empty out."""
    stripped = (text or "").strip()
    if not stripped:
        return []
    return [piece.strip() for piece in _SPLIT_RE.split(stripped) if piece.strip()]
