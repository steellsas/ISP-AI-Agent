"""
Deterministic address extraction (NLU Track A) — docs/pokalbio_variklis.md §4.

Pulls city / street / house / apartment out of a (number-normalized) STT
utterance WITHOUT the LLM, by fuzzy-matching word n-grams against the streets
registry and reading numbers via the LT normalizer. This is the reliable FLOOR:
the LLM can still segment complex multi-clause sentences (Track B), but a clean
address never depends on it, and the extractor can only return a street that
actually exists in the registry (no hallucination).

Pure function `extract_address(text, streets, localities)` is unit-testable with
hand-given registry lists; `load_registry(db)` is the thin DB-backed loader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from adapters.asr.lt_text import normalize_lt_numbers
from crm_mcp.tools.address_resolver import locality_match_score, street_match_score

# A token is a number (optionally with a trailing letter: "122F") or a word.
_TOKEN_RE = re.compile(r"(?P<num>\d+[^\W\d_]?)|(?P<word>[^\W\d_]+)", re.UNICODE)
_STREET_THRESHOLD = 0.75
_CITY_THRESHOLD = 0.85


@dataclass
class AddressReading:
    city: str | None = None
    street: str | None = None  # the REGISTRY street name (validated to exist)
    house: str | None = None
    apartment: str | None = None
    street_confidence: float = 0.0


def _tokenize(text: str) -> list[tuple[str, str]]:
    """[(kind, value), ...] where kind is 'num' or 'word', in spoken order."""
    seq: list[tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(text):
        if m.group("num"):
            seq.append(("num", m.group("num")))
        else:
            seq.append(("word", m.group("word")))
    return seq


def _best_span(
    seq: list[tuple[str, str]],
    candidates: list[str],
    score_fn,
    threshold: float,
    *,
    max_n: int = 3,
    exclude: set[int] | None = None,
) -> tuple[float, str | None, int, int]:
    """
    Best registry match over contiguous word n-grams (length 1..max_n).

    Returns (score, candidate_value, start_seq_idx, end_seq_idx). Spans that
    overlap `exclude` (already-claimed token indices) are skipped, so the city
    search never reuses the street's tokens.
    """
    exclude = exclude or set()
    word_idx = [i for i, (k, _) in enumerate(seq) if k == "word" and i not in exclude]
    best: tuple[float, str | None, int, int] = (0.0, None, -1, -1)
    for a in range(len(word_idx)):
        for n in range(1, max_n + 1):
            if a + n > len(word_idx):
                break
            idxs = word_idx[a : a + n]
            # Must be contiguous in the token sequence (no number between words).
            if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
                continue
            phrase = " ".join(seq[i][1] for i in idxs)
            for cand in candidates:
                s = score_fn(phrase, cand)
                if s > best[0]:
                    best = (s, cand, idxs[0], idxs[-1])
    if best[0] >= threshold:
        return best
    return (0.0, None, -1, -1)


def extract_address(
    text: str,
    streets: list[str],
    localities: list[str],
) -> AddressReading:
    """
    Deterministic city/street/house/apartment from one utterance (no LLM).

    Numbers are normalized first ("keturiasdešimt keturi" -> "44"). The street is
    the best registry n-gram match >= threshold; the city the best locality match
    among the remaining words. House = the first number after the street (or the
    first number); apartment = the number right after a "but*" marker.
    """
    norm = normalize_lt_numbers(text or "")
    seq = _tokenize(norm)
    if not seq:
        return AddressReading()

    sc, street, s_start, s_end = _best_span(seq, streets, street_match_score, _STREET_THRESHOLD)
    street_span = set(range(s_start, s_end + 1)) if street else set()
    _, city, _, _ = _best_span(
        seq, localities, locality_match_score, _CITY_THRESHOLD, max_n=2, exclude=street_span
    )

    nums = [(i, v) for i, (k, v) in enumerate(seq) if k == "num"]

    # apartment = first number after a "but*" marker word
    apt = None
    apt_i = None
    for i, (k, v) in enumerate(seq):
        if k == "word" and v.lower().startswith("but"):
            nxt = next(((j, nv) for j, nv in nums if j > i), None)
            if nxt:
                apt_i, apt = nxt
            break

    # house = first remaining number after the street span (else the first one)
    house = None
    rest = [(j, v) for j, v in nums if j != apt_i]
    if street is not None:
        after = [(j, v) for j, v in rest if j > s_end]
        pick = after or rest
    else:
        pick = rest
    if pick:
        house = pick[0][1]

    return AddressReading(
        city=city, street=street, house=house, apartment=apt, street_confidence=sc
    )


# --- Problem classification (R1) ---------------------------------------------
# Deterministic keyword classifier for the stated problem. A first hypothesis,
# revisable on a later turn (docs/pokalbio_variklis.md §12.2). Order matters:
# more specific first ("lėtas internetas" -> slow, not down).
_PROBLEM_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("internet_slow", ("lėtas", "lėtai", "lėta", "stringa", "lūžinėja", "buferiuoja")),
    ("tv", ("televizij", "televizor", " tv", "kanalai", "kanalų")),
    ("billing", ("sąskait", "mokė", "skola", "kaina", "tarif")),
    ("internet_down", ("internet", "ryši", "ryšys", "neveikia", "nėra interneto", "wifi", "wi-fi")),
)


def classify_problem(text: str) -> str | None:
    """Best-effort problem type from the utterance (keyword match), or None."""
    low = f" {(text or '').lower()} "
    for problem, keywords in _PROBLEM_KEYWORDS:
        if any(kw in low for kw in keywords):
            return problem
    return None


# --- Symptom extraction (A3) -------------------------------------------------
# Deterministic categorical symptoms from the utterance. Order WITHIN a category
# matters (negations/specifics first: "nedega" before "dega"). Free-form symptoms
# (exact onset time) are left to the LLM / a future SLM (§12.7).
_SYMPTOM_KEYWORDS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    # STT-tolerant stems (Whisper mishears "nedega"->"nedaga", "dega"->"dagą").
    # Order matters: negation/specific first ("nedeg" before "deg").
    "lights": (
        ("nedega", ("nedeg", "nedag", "užges", "negyv", "nešvie")),
        ("mirksi", ("mirks", "mirg", "blyks")),
        ("dega", ("dega", "dag", "švie", "žali")),
    ),
    "connection": (
        ("wifi", ("wifi", "wi-fi", "vaifai", "belaid", "beviel")),
        ("laidinis", ("laid", "kabel")),
    ),
    "devices": (
        ("visi", ("visi", "visur", "visuose", "viskas")),
        ("vienas", ("viename", "tik vien", "vienam", "vienas įreng")),
    ),
    "frequency": (
        ("nuolat", ("nuolat", "visada", "visą laiką")),
        ("protarpiais", ("kartais", "protarpiais", "retkarčiais", "dingsta", "lūžinėja")),
    ),
    "services": (
        ("tv", ("televizij", "televizor", "kanal")),
        ("telefonas", ("telefon",)),
    ),
}


def extract_symptoms(text: str) -> dict[str, str]:
    """Categorical symptoms present in the utterance, e.g. {'lights': 'nedega'}."""
    low = f" {(text or '').lower()} "
    out: dict[str, str] = {}
    for category, options in _SYMPTOM_KEYWORDS.items():
        for value, keywords in options:
            if any(kw in low for kw in keywords):
                out[category] = value
                break
    return out


def load_registry(db) -> tuple[list[str], list[str]]:
    """(street names with their 'g.' suffix, sorted locality names) from the DB."""
    with db.cursor() as cursor:
        cursor.execute("SELECT street_name, street_type, city FROM streets")
        rows = [dict(r) for r in cursor.fetchall()]
    streets = [f"{r['street_name']} {r['street_type'] or 'g.'}".strip() for r in rows]
    localities = sorted({r["city"] for r in rows})
    return streets, localities
