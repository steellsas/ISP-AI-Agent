"""
Lithuanian language algorithms — what a word list cannot express.

Reached through agent.contract.locale.lang(); another language provides a module
with the same functions.
"""

from __future__ import annotations

import re

# Spoken number words -> digits ("šešiasdešimt" -> 60), shared with the ASR adapter.
from adapters.asr.lt_text import normalize_lt_numbers as normalize_numbers  # noqa: F401

# STT routinely drops Lithuanian diacritics ("Tai ikištas", "razetė") — keyword
# matches fold BOTH sides so a dropped nosinė never hides a fact.
_DEACCENT = str.maketrans("ąčęėįšųūž", "aceeisuuz")


def deaccent(text: str) -> str:
    """Lithuanian diacritics -> base letters (case kept)."""
    return text.translate(_DEACCENT)


def fold(text: str) -> str:
    """Lower-cased and deaccented, for tolerant marker matching."""
    return text.lower().translate(_DEACCENT)


# Month names: accusative ("skola už liepą") and genitive ("birželio 5 d."),
# keyed by the two-digit month.
_MONTH_ACC = {
    "01": "sausį", "02": "vasarį", "03": "kovą", "04": "balandį",
    "05": "gegužę", "06": "birželį", "07": "liepą", "08": "rugpjūtį",
    "09": "rugsėjį", "10": "spalį", "11": "lapkritį", "12": "gruodį",
}  # fmt: skip
_MONTH_GEN = {
    "01": "sausio", "02": "vasario", "03": "kovo", "04": "balandžio",
    "05": "gegužės", "06": "birželio", "07": "liepos", "08": "rugpjūčio",
    "09": "rugsėjo", "10": "spalio", "11": "lapkričio", "12": "gruodžio",
}  # fmt: skip


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 9 and not 11 <= n % 100 <= 19:
        return few
    return many


def money(amount: float) -> str:
    """TTS-friendly money: 49.98 -> "49 eurai 98 centai" (correct plural forms)."""
    eur = int(amount)
    ct = round((amount - eur) * 100)
    text = f"{eur} {_plural(eur, 'euras', 'eurai', 'eurų')}"
    if ct:
        text += f" {ct} {_plural(ct, 'centas', 'centai', 'centų')}"
    return text


def months(periods: list[str]) -> str | None:
    """['2026-07','2026-08'] -> "liepą ir rugpjūtį"."""
    names = [_MONTH_ACC.get(p[5:7]) for p in periods if len(p) >= 7]
    names = [n for n in names if n]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " ir " + names[-1]


def date(value: str | None) -> str | None:
    """'2026-06-05' -> "birželio 5 d."."""
    if not value or len(value) < 10:
        return None
    month = _MONTH_GEN.get(value[5:7])
    try:
        day = int(value[8:10])
    except ValueError:
        return None
    return f"{month} {day} d." if month else None


# "Tilžės g. 60-7" is written form — TTS reads it "g. šešiasdešimt minus septyni".
# Speak addresses like a human: "Tilžės gatvė, namas 60, butas 7".
_ADDR_HOUSE_FLAT = re.compile(r"\bg\.\s*(\d+)\s*-\s*(\d+)\b")
_ADDR_HOUSE = re.compile(r"\bg\.(?=\s*\d)")
_ADDR_ABBR = re.compile(r"\bg\.(?=\s|$)")


def speech_text(text: str) -> str:
    """The spoken form of a reply for TTS: 'X g. 60-7' -> 'X gatvė, namas 60,
    butas 7', 'X g. 60' -> 'X gatvė 60', a dangling 'g.' -> 'gatvė'."""
    if not text or "g." not in text:
        return text
    out = _ADDR_HOUSE_FLAT.sub(r"gatvė, namas \1, butas \2", text)
    out = _ADDR_HOUSE.sub("gatvė", out)
    return _ADDR_ABBR.sub("gatvė", out)
