"""
Lithuanian ASR text helpers — recover accuracy WITHOUT a bigger (slower) model.

On CPU a large Whisper model is too slow for live voice, so we keep a small/
medium model fast and claw back accuracy with two cheap, deterministic tools:

1. DOMAIN_PROMPT_LT — a Whisper `initial_prompt` naming the exact cities,
   villages, streets and domain words the agent will hear. Whisper biases its
   decoding toward vocabulary present in the prompt, so this fixes proper-noun
   recognition ("Telviazgai" -> "Tilžės") for free.

2. normalize_lt_numbers — turns spoken Lithuanian number words in a transcript
   into digits BEFORE the LLM ("šešiasdešimt" -> "60", "butas septintas" ->
   "butas 7"). Whisper transcribes the words; the agent needs digits for
   resolve_address. Belt-and-suspenders with the prompt's "convert numbers"
   rule, and far more reliable for house/apartment numbers.

Both are voice-input helpers (the typed CLI path needs neither).
"""

from __future__ import annotations

import re

# Common Whisper hallucinations on silence/noise (it emits frequent training
# artefacts when there is no real speech). Observed live: "www.youtube.come".
# Matched case-insensitively as a substring of the stripped transcript.
_HALLUCINATION_MARKERS = (
    "youtube.com",
    "youtube",
    "amara.org",
    "subtitles",
    "subscribe",
    "thanks for watching",
    "ačiū, kad žiūrėjote",
    "ačiū kad žiūrėjote",
    "redaguota",
    "продолжение следует",
)


def is_asr_noise(text: str) -> bool:
    """True when an ASR result is empty or a likely silence/noise hallucination.

    Voice-only guard: such a "turn" should be ignored (the agent stays silent and
    waits for real speech) rather than answered. Conservative — it does not drop
    short real words like "taip"/"gerai"/"nu".
    """
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    low = stripped.lower()
    if any(marker in low for marker in _HALLUCINATION_MARKERS):
        return True
    # A URL is never a real spoken answer when reporting no internet.
    if "www." in low or "http" in low:
        return True
    # Nothing but punctuation/symbols (no letters or digits) -> noise.
    return not re.search(r"[^\W_]", stripped, re.UNICODE)


# --- Whisper domain prime (proper nouns + vocabulary it must spell right) -----
# Kept short (Whisper's initial_prompt is ~224 tokens) and focused on the demo's
# localities/streets plus the words that recur in ISP support.
DOMAIN_PROMPT_LT = (
    "Pokalbis su interneto paslaugų tiekėjo klientų aptarnavimu lietuvių kalba. "
    "Klientas sako adresą: miestą, gatvę, namo numerį ir butą. "
    "Miestai ir vietovės: Šiauliai, Šiaulių rajonas, Ginkūnai, Bubiai, Vinkšnėnai. "
    "Gatvės: Tilžės gatvė, Dainų gatvė, Dailės gatvė, Žemaitės gatvė, "
    "Vilniaus gatvė, S. Dariaus ir S. Girėno gatvė, Žeimių gatvė, Aušros gatvė, "
    "Sodo gatvė. "
    "Žodžiai: internetas, ryšys, greitis, gedimas, sąskaita, sutartis, "
    "routeris, maršrutizatorius, laidas, lemputė, abonento kodas."
)


# --- Lithuanian number words -> integers --------------------------------------
_UNITS = {
    "nulis": 0,
    "vienas": 1,
    "viena": 1,
    "vieną": 1,
    "du": 2,
    "dvi": 2,
    "trys": 3,
    "tris": 3,
    "keturi": 4,
    "keturios": 4,
    "keturias": 4,
    "keturės": 4,
    "penki": 5,
    "penkios": 5,
    "penkias": 5,
    "penkės": 5,
    "šeši": 6,
    "šešios": 6,
    "šešias": 6,
    "šešės": 6,
    "šešis": 6,  # common Whisper variant, e.g. split "šešis dešimt" -> 60
    "septyni": 7,
    "septynios": 7,
    "septynias": 7,
    "septynės": 7,
    "aštuoni": 8,
    "aštuonios": 8,
    "aštuonias": 8,
    "aštuonės": 8,
    "devyni": 9,
    "devynios": 9,
    "devynias": 9,
    "devynės": 9,
    # Whisper sometimes hears the genitive "-ių" for these units.
    "šešių": 6,
    "penkių": 5,
    "keturių": 4,
}
_TEENS = {
    "dešimt": 10,
    "vienuolika": 11,
    "dvylika": 12,
    "trylika": 13,
    "keturiolika": 14,
    "penkiolika": 15,
    "šešiolika": 16,
    "septyniolika": 17,
    "aštuoniolika": 18,
    "devyniolika": 19,
}
_TENS = {
    "dvidešimt": 20,
    "trisdešimt": 30,
    "keturiasdešimt": 40,
    "penkiasdešimt": 50,
    "šešiasdešimt": 60,
    "septyniasdešimt": 70,
    "aštuoniasdešimt": 80,
    "devyniasdešimt": 90,
    # common Whisper misspellings heard in real recordings
    "šešesdešimt": 60,
    "penkesdešimt": 50,
    "keturesdešimt": 40,
}
_HUNDRED = {"šimtas": 100, "šimtai": 100, "šimtų": 100, "šimto": 100}
# Ordinals (house/apartment are often spoken as "butas septintas" = 7).
_ORDINALS = {
    "pirmas": 1,
    "pirma": 1,
    "pirmą": 1,
    "antras": 2,
    "antra": 2,
    "antrą": 2,
    "trečias": 3,
    "trečia": 3,
    "trečią": 3,
    "ketvirtas": 4,
    "ketvirta": 4,
    "ketvirtą": 4,
    "penktas": 5,
    "penkta": 5,
    "penktą": 5,
    "šeštas": 6,
    "šešta": 6,
    "šeštą": 6,
    "septintas": 7,
    "septinta": 7,
    "septintą": 7,
    "septintį": 7,
    "aštuntas": 8,
    "aštunta": 8,
    "aštuntą": 8,
    "devintas": 9,
    "devinta": 9,
    "devintą": 9,
    "dešimtas": 10,
    "dešimta": 10,
    "dešimtą": 10,
}

_ALL_NUMBER_WORDS = {**_UNITS, **_TEENS, **_TENS, **_HUNDRED, **_ORDINALS}

# A token is "word-ish" if it is letters only (so we don't touch existing digits).
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _classify(token: str) -> str | None:
    t = token.lower()
    if t in _HUNDRED:
        return "hundred"
    if t in _TENS:
        return "tens"
    if t in _TEENS:
        return "teens"
    if t in _UNITS:
        return "unit"
    if t in _ORDINALS:
        return "ordinal"
    return None


def _run_value(words: list[str]) -> int:
    """Combine a run of consecutive LT number words into one integer.

    Digit-sequence first: a run of ONLY bare units (0-9), two or more long, is
    spoken digits — "šeši nulis" -> 60, "šeši aštuoni" -> 68 — so concatenate them.
    A real compound number always contains a tens/teens/hundred word, so this
    never mis-fires on "šešiasdešimt aštuoni" (= 68 by arithmetic below). This is
    what makes the digit-by-digit fallback ("pasakykite skaitmenimis") work.
    """
    if len(words) >= 2 and all(_classify(w) == "unit" for w in words):
        return int("".join(str(_UNITS[w.lower()]) for w in words))

    total = 0
    pending = 0  # a bare unit: multiplier before 'šimtai', else the ones digit
    for w in words:
        t = w.lower()
        kind = _classify(t)
        if kind == "hundred":
            total += (pending or 1) * 100
            pending = 0
        elif kind == "tens":
            total += _TENS[t]
            pending = 0
        elif kind == "teens":
            # STT often splits a single ten-word: "šešias dešimt" -> 6 + "dešimt".
            # A unit (2-9) immediately before "dešimt" means unit*10 (= 60).
            if t == "dešimt" and 2 <= pending <= 9:
                total += pending * 10
            else:
                total += _TEENS[t]
            pending = 0
        elif kind == "unit":
            pending = _UNITS[t]
        elif kind == "ordinal":
            pending = _ORDINALS[t]
    return total + pending


def normalize_lt_numbers(text: str) -> str:
    """Replace runs of spoken Lithuanian number words with digits.

    "Tilžės gatvė šešiasdešimt butas septintas" ->
    "Tilžės gatvė 60 butas 7".  Non-number words and existing digits are
    left untouched. Punctuation/spacing between number words is preserved
    loosely (a run collapses to a single number).
    """
    if not text:
        return text

    out: list[str] = []
    run: list[str] = []
    last_end = 0

    def flush_run() -> None:
        if run:
            out.append(str(_run_value(run)))
            run.clear()

    for m in _TOKEN_RE.finditer(text):
        gap = text[last_end : m.start()]
        word = m.group(0)
        last_end = m.end()
        if _classify(word) is not None:
            # Inside a number run: swallow the gap (collapse "šešiasdešimt penki").
            if not run:
                out.append(gap)  # keep separator before the run starts
            run.append(word)
        else:
            flush_run()
            out.append(gap)
            out.append(word)

    flush_run()
    out.append(text[last_end:])
    return "".join(out)
