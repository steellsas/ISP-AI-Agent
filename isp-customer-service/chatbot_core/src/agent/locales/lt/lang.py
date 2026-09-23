"""
Lithuanian language algorithms — what a word list cannot express.

Reached through agent.contract.locale.lang(); another language provides a module
with the same functions.
"""

from __future__ import annotations

import re

# The language's name in English, for prompts ("the call is held in Lithuanian").
LANGUAGE_NAME = "Lithuanian"

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


# ADRESAS BALSU (Andrius, 2026-09-23). Rašoma forma "Šiaulių r., Ginkūnų k., Žeimių g. 12-6"
# skaitoma kaip santrumpų sąrašas; žmogus pasakytų "Šiaulių rajone, Ginkūnų kaime, Žeimių
# gatvėje 12, butas 6". Todėl prieš TTS: namas-butas išskiriamas, santrumpos ištariamos
# pilnai, o vietovė prieš gatvę — vietininku.
#
# Linksnis priklauso nuo sakinio: pasakant adresą — vietininkas ("Šiauliuose, Tilžės gatvėje
# 60, butas 3"), o po "dėl" — kilmininkas ("Ar skambinate dėl Tilžės gatvės 60, buto 3?").
_ADDR_HOUSE_FLAT = re.compile(r"\bg\.\s*(\d+)\s*-\s*(\d+)\b")
_ADDR_FLAT = re.compile(r"\bbutas\s+(\d+)\b")
# santrumpa -> (vietininkas, kilmininkas)
_ADDR_ABBREV = (
    (re.compile(r"\bg\.(?=\s*\d|\s|,|$)"), ("gatvėje", "gatvės")),
    (re.compile(r"\bk\.(?=\s|,|$)"), ("kaime", "kaimo")),
    (re.compile(r"\br\.(?=\s|,|$)"), ("rajone", "rajono")),
    (re.compile(r"\bpr\.(?=\s*\d|\s|,|$)"), ("prospekte", "prospekto")),
    (re.compile(r"\bal\.(?=\s*\d|\s|,|$)"), ("alėjoje", "alėjos")),
    (re.compile(r"\bsav\.(?=\s|,|$)"), ("savivaldybėje", "savivaldybės")),
)
# Vardininkas -> vietininkas pagal galūnę (ilgiausia pirma). Nežinomos galūnės vardas lieka
# nepakeistas — geriau neįprastas vardininkas negu sugalvota forma.
_PLACE_LOCATIVE = (
    ("iai", "iuose"),  # Šiauliai -> Šiauliuose, Telšiai -> Telšiuose
    ("ai", "uose"),  # Ginkūnai -> Ginkūnuose
    ("ius", "iuje"),  # Vilnius -> Vilniuje
    ("ys", "yje"),  # Panevėžys -> Panevėžyje
    ("us", "uje"),  # Alytus -> Alytuje
    ("as", "e"),  # Kaunas -> Kaune
    ("ė", "ėje"),  # Plungė -> Plungėje
    ("a", "oje"),  # Klaipėda -> Klaipėdoje
)
# Vietovė, po kurios (per kablelį) seka gatvė — būtent ji sakoma vietininku. "Šiaulių r."
# lieka kilmininkas + "rajone", nes taip ir sako žmonės.
_PLACE_BEFORE_STREET = re.compile(
    r"\b([A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+),(?=[^,]*?(?:\bg\.|\bpr\.|\bal\.|gatvėje|prospekte))"
)
# "dėl" prieš adresą reikalauja kilmininko; ieškom jo tik toje pačioje sakinio dalyje.
_DEL_BEFORE = re.compile(r"\bd[eė]l\b[^.!?]{0,40}$", re.IGNORECASE)


def _genitive_here(text: str, pos: int) -> bool:
    return bool(_DEL_BEFORE.search(text[:pos]))


def _locative(word: str) -> str:
    """The inessive ("kur?") of a place name, or the name unchanged."""
    for end, loc in _PLACE_LOCATIVE:
        if word.endswith(end):
            return word[: -len(end)] + loc
    return word


def speech_text(text: str) -> str:
    """The spoken form of a reply for TTS.

    "Šiauliai, Tilžės g. 60-3" -> "Šiauliuose, Tilžės gatvėje 60, butas 3"
    "Šiaulių r., Ginkūnų k., Žeimių g. 12-6" -> "Šiaulių rajone, Ginkūnų kaime,
    Žeimių gatvėje 12, butas 6"
    "Ar skambinate dėl Tilžės g. 60, butas 3?" -> "... dėl Tilžės gatvės 60, buto 3?"
    """
    if not text:
        return text

    def _place(m: re.Match[str]) -> str:
        if _genitive_here(text, m.start()):
            return m.group(0)  # po "dėl" vietovė jau kilmininke ("dėl Šiaulių, ...")
        return _locative(m.group(1)) + ","

    out = _PLACE_BEFORE_STREET.sub(_place, text)

    def _house_flat(m: re.Match[str]) -> str:
        if _genitive_here(out, m.start()):
            return f"gatvės {m.group(1)}, buto {m.group(2)}"
        return f"gatvėje {m.group(1)}, butas {m.group(2)}"

    out = _ADDR_HOUSE_FLAT.sub(_house_flat, out)
    for pattern, (locative, genitive) in _ADDR_ABBREV:

        def _case(m: re.Match[str], loc=locative, gen=genitive, seen=out) -> str:
            # `seen` is bound on purpose: the case depends on the text as it was BEFORE this
            # substitution, which is what carries the "dėl" that decides it.
            return gen if _genitive_here(seen, m.start()) else loc

        out = pattern.sub(_case, out)

    def _flat(m: re.Match[str], seen=out) -> str:
        return f"buto {m.group(1)}" if _genitive_here(seen, m.start()) else m.group(0)

    return _ADDR_FLAT.sub(_flat, out)
