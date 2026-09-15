"""
Deterministic address extraction (NLU Track A) — docs/pokalbio_variklis.md §4.

Pulls city / street / house / apartment out of a (number-normalized) STT
utterance WITHOUT the LLM, by fuzzy-matching word n-grams against the streets
registry and reading numbers via the LT normalizer. This is the reliable FLOOR:
the LLM can still segment complex multi-clause sentences (Track B), but a clean
address never depends on it, and the extractor can only return a street that
actually exists in the registry (no hallucination).

Pure function `extract_address(text, streets, localities)` is unit-testable with
hand-given registry lists (the gateway's address_registry() provides them).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import limits
from .contract.locale import lang, vocab, vocab_map, vocab_re, vocab_set, vocab_text
from .tooling.address_matching import locality_match_score, street_match_score

# A token is a number (optionally with a trailing letter: "122F") or a word.
_TOKEN_RE = re.compile(r"(?P<num>\d+[^\W\d_]?)|(?P<word>[^\W\d_]+)", re.UNICODE)


def _deaccent(word: str) -> str:
    """Diacritics -> base letters for tolerant marker matching (STT often writes
    the long-vowel form: "būtos" for "butas"). Keyword prefixes only, not values."""
    from .contract.locale import lang

    return lang().deaccent(word)


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
    # NLU wave block 1 (live 2026-09-08: "Tildžės 6 0 būtų namas" read house=6):
    # two adjacent SINGLE-digit tokens are one spoken number ("šeši nulis" =
    # 60), not two values — glue the pair. Longer digits never glue, so
    # "Vilniaus 33 2" keeps its two numbers.
    glued: list[tuple[str, str]] = []
    for k, v in seq:
        if (
            k == "num"
            and len(v) == 1
            and glued
            and glued[-1][0] == "num"
            and len(glued[-1][1]) == 1
        ):
            glued[-1] = ("num", glued[-1][1] + v)
            continue
        glued.append((k, v))
    return glued


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
    norm = lang().normalize_numbers(text or "")
    seq = _tokenize(norm)
    if not seq:
        return AddressReading()

    sc, street, s_start, s_end = _best_span(
        seq, streets, street_match_score, limits.get("nlu_street_match_threshold")
    )
    street_span = set(range(s_start, s_end + 1)) if street else set()
    _, city, _, _ = _best_span(
        seq,
        localities,
        locality_match_score,
        limits.get("nlu_city_match_threshold"),
        max_n=2,
        exclude=street_span,
    )

    nums = [(i, v) for i, (k, v) in enumerate(seq) if k == "num"]

    # NLU wave block 1 (live P2, 2026-09-08): word ANCHORS decide the slot.
    # "Tai but... but NAMO numeris yra 60" put 60 into the APARTMENT (the
    # truncated "but" matched the flat marker); "60 būtų namas" lost the
    # house. The number nearest to an explicit house word (namo/namas/namą,
    # within 3 tokens either side) is the HOUSE — no marker may claim it.
    house_anchor = None
    house_anchor_i = None
    for i, (k, v) in enumerate(seq):
        if k == "word" and _deaccent(v.lower()) in vocab_set("house_words"):
            near = [(abs(j - i), j, nv) for j, nv in nums if abs(j - i) <= 3]
            if near:
                _, house_anchor_i, house_anchor = min(near)
            break

    # apartment = first number after a "but*" marker word. De-accent the word first so
    # STT long-vowel spellings ("būtos", "būto") still match the "but" marker — observed:
    # "Tilžės 60 būtos 3" left apartment=None, so the caller's flat was silently ignored.
    # Block 1: a 3-letter "but" (usually a truncated "bet") is NOT a marker,
    # and the house-anchored number is never the apartment.
    apt = None
    apt_i = None
    for i, (k, v) in enumerate(seq):
        if (
            k == "word"
            and _deaccent(v.lower()).startswith(vocab("apartment_marker"))
            and len(v) >= 4
        ):
            nxt = next(((j, nv) for j, nv in nums if j > i and j != house_anchor_i), None)
            if nxt:
                apt_i, apt = nxt
            break

    # house = the anchored number first; else the first remaining number after
    # the street span (else the first one).
    house = house_anchor
    rest = [(j, v) for j, v in nums if j != apt_i and j != house_anchor_i]
    if house is None:
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
# The stated problem from the utterance: the knowledge catalog's triggers
# (`knowledge/faults.yaml`); a first hypothesis, revisable on a later turn.


def classify_problem(text: str) -> str | None:
    """Best-effort problem type (the call's PURPOSE) from the utterance, or None.

    Reads the DECLARATIVE triggers in `knowledge/faults.yaml` — adding a problem is a
    file edit."""
    low = f" {(text or '').lower()} "
    # Negation guard FIRST — before EITHER trigger layer (2026-09-02, live G2:
    # "interneto bėdų NETURIU, tik dėl sąskaitos" committed internet_down via
    # the bare trigger and the agent asked "kada dingo?"): a denied problem is
    # not a problem statement.
    if any(m in low for m in vocab("no_problem_marks")):
        return None
    from .faults import classify_purpose

    return classify_purpose(text)


def classify_problem_llm(text: str | None, model: str | None = None) -> tuple[str | None, float]:
    """L2 of the classification cascade (DIALOGO_ETALONAS, 2026-09-02): when
    the trigger layer catches nothing, the LLM reads the CONTEXT against the
    file-declared catalog (description + examples per type) — "niekas man
    nekrauna" is internet_down without any trigger enumeration. Returns
    (type, confidence) or (None, 0.0); the CALLER decides what a given
    confidence earns (commit / explicit confirm / keep asking). Fail-soft:
    any error is (None, 0.0) — the gate ladder continues as before."""
    if not text or not text.strip():
        return None, 0.0
    try:
        from .classifier import classify_step
        from .faults import problem_catalog_options

        options = problem_catalog_options()
        if not options:
            return None, 0.0
        from .prompts import load_node_prompt

        obs = classify_step(
            load_node_prompt("sensors/problem_classifier"),
            text,
            options,
            model=model,
        )
        if obs is None or not obs.is_answer or obs.label not in options:
            return None, 0.0
        return str(obs.label), float(obs.confidence or 0.0)
    except Exception:  # pragma: no cover - defensive; the gate keeps working
        return None, 0.0


def extract_symptoms(text: str) -> dict[str, str]:
    """Categorical symptoms present in the utterance, e.g. {'lights': 'nedega'}."""

    # STT splits the negation prefix ("ne dega" for "nedega") — glue a bare
    # "ne " to the following word so polarity survives (live 2026-08-20: the
    # SYMPTOMS line said dega while the ledger said nedega and the narrator
    # got a contradiction). "ne," stays split — that is a real standalone no.
    glued = vocab_re("split_negation").sub(vocab_text("split_negation_glued"), (text or "").lower())
    low = f" {glued} "
    out: dict[str, str] = {}
    for category, options in vocab_map("symptom_keywords").items():
        for value, keywords in options:
            if any(kw in low for kw in keywords):
                out[category] = value
                break
    return out


# --- Anamnesis reading (Step 2, the ANALYSIS object) -------------------------------
# The intake question is "kada pastebėjote, kad dingo — gal po ko nors?"; the answer
# carries WHEN it broke and an optional TRIGGER event. Keyword-read, best-effort —
# the raw text is kept alongside either way.


def extract_anamnesis(text: str | None) -> dict:
    """{'when': str|None, 'trigger': str|None} from the intake anamnesis answer.
    'nežino' is a valid reading: an explicit "nežinau" with no other signal."""
    out: dict = {"when": None, "trigger": None}
    if not text:
        return out
    low = text.lower()
    for label, marks in vocab("anamnesis_when"):
        if any(m in low for m in marks):
            out["when"] = label
            break
    for label, marks in vocab("anamnesis_trigger"):
        if any(m in low for m in marks):
            out["trigger"] = label
            break
    if out["when"] is None and any(m in low for m in vocab("dont_know")):
        out["when"] = "unknown"
    return out
