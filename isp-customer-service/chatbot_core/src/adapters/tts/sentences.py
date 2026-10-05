"""Sentence splitting for streaming TTS — turn a reply into speakable chunks.

Streaming adapters synthesize and play one sentence at a time so the caller hears
the start of the reply before the whole thing is rendered (Pillar C). Kept tiny
and shared so gTTS and edge-tts chunk identically.
"""

from __future__ import annotations

import re

# Split AFTER sentence-final punctuation (keeping it) and on line breaks.
_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+", re.UNICODE)


# Kaip DIKTUOJAMAS techninis tekstas. Balsas skaito „192.168.0.1" kaip skaičių („šimtas
# devyniasdešimt du tūkstančiai…"), ir klientas tokio adreso neįveda — gyvai 2026-10-05 Andrius:
# *„turėtų diktuojama kaip IP adresas: 192 taškas 168 taškas 1 taškas 1."* Ilgas skaičius dar ir
# ištęsia ėjimą, tad tai pataiso ir laiką.
_IP_RE = re.compile(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})")
# „admin/admin", „Save / Apply" — pasvirasis brūkšnys balse tampa PAUZE, ne žodžiu: „admin arba
# admin" būtų netiesa (tai vardas IR slaptažodis), o „slash" klientui nieko nesako.
_SLASH_RE = re.compile(r"(?<=\w)\s*/\s*(?=\w)")
_DOT_WORD = {"lt": "taškas", "en": "dot"}


def speakable(text: str, language: str | None = "lt") -> str:
    """Tas pats sakinys, bet DIKTUOJAMAS: IP adresas po gabalo, pasvirasis brūkšnys — pauzė.

    Taikoma tik prieš sintezę; ekrane, trace'e ir tikete tekstas lieka toks, kokį parašė agentas.
    """
    lang = (language or "lt").split("-")[0].lower()
    dot = _DOT_WORD.get(lang, _DOT_WORD["en"])
    spoken = _IP_RE.sub(lambda m: f" {dot} ".join(m.groups()), text or "")
    spoken = _SLASH_RE.sub(", ", spoken)
    return spoken


def split_sentences(text: str) -> list[str]:
    """['Sveiki.', 'Ar veikia?'] from 'Sveiki. Ar veikia?' — empty in, empty out."""
    stripped = (text or "").strip()
    if not stripped:
        return []
    return [piece.strip() for piece in _SPLIT_RE.split(stripped) if piece.strip()]


# Pop the FIRST complete sentence from a growing buffer (LLM token streaming, C3):
# a sentence is complete once its ending punctuation is followed by whitespace.
_POP_RE = re.compile(r"^(.*?[.!?…])\s+(.*)$", re.DOTALL)


def pop_sentence(buffer: str) -> tuple[str | None, str]:
    """(first_complete_sentence, remainder) — (None, buffer) if none is complete yet."""
    m = _POP_RE.match(buffer)
    if m and m.group(1).strip():
        return m.group(1).strip(), m.group(2)
    return None, buffer
