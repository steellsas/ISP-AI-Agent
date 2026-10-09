"""Evidence ledger — Ledger v1 (Phase 4.5, spec agreed 2026-08-05).

The call's position is WHAT IS KNOWN, not which step number. Facts live in
`state.evidence` as {key: entry} with SOURCE and full history:

    entry = {"value", "source", "turn", "history": [...], "conflict": bool}

Two sources, not equal:
- TELEMETRY (tools) — ground truth; overwrites the value (history kept);
  the caller's words never overwrite a telemetry fact.
- CLIENT — fills only what telemetry cannot see (lights, cables, devices at
  home). A DIFFERENT canonical client value flags a CONFLICT instead of
  silently overwriting — the engine then asks ONE scripted clarification
  ("sakėte X, dabar Y — kaip yra iš tiesų?"), and the next answer resolves it.

v1 extraction is the deterministic keyword pass below (no LLM call, testable,
STT-garble tolerant); the LLM extractor upgrade rides on the same keys later.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from .contract.locale import vocab, vocab_map, vocab_re

TELEMETRY = "telemetry"


class Contradiction(BaseModel):
    """Something contradicts what the call believes (D-05) — it only puts the belief in
    doubt; one confirm question settles it.

    kind: conflict — a client fact against the client's earlier value ("sakėte X, dabar
          Y — kaip yra iš tiesų?"); flip — a volunteered story-flipping fact parked
          before it may enter the ledger; refute — a client fact that refutes the
          hypothesis, confirmed before the pivot; verdict — a telemetry recheck names
          another cause.
    asked: False = the confirm question is due (doubt), True = it is out (confirming).
    """

    kind: Literal["conflict", "flip", "refute", "verdict"]
    source: Literal["client", "telemetry", "analyst"] = "client"
    fact_key: str
    before_value: str | None = None
    now_value: str | None = None
    before_quote: str | None = None  # what the client said earlier, for the question
    asked: bool = False
    asks: int = 0


CLIENT = "client"
# The give-up marker: the caller's answer could not be read (replaceable by any real value).
UNKNOWN = "unknown"


def set_fact(
    evidence: dict[str, Any], key: str, value: str, source: str, turn: int
) -> dict[str, Any]:
    """Record a fact; returns the entry. Telemetry overwrites; a different
    CLIENT value on a client fact flags a conflict (resolved by the next
    client value for the same key — the clarify answer)."""
    entry = evidence.get(key)
    stamp = {"value": value, "source": source, "turn": turn}
    if entry is None:
        entry = {**stamp, "history": [stamp], "conflict": False}
        evidence[key] = entry
        return entry
    entry["history"].append(stamp)
    if source == TELEMETRY:
        entry.update(stamp)
        entry["conflict"] = False
        return entry
    # client value onto a telemetry-backed fact: words never overwrite.
    if entry["source"] == TELEMETRY:
        return entry
    if entry["value"] == UNKNOWN:
        # Our own give-up marker — any real value replaces it, no conflict.
        entry.update(stamp)
        entry["conflict"] = False
        return entry
    if entry["conflict"]:
        # The clarify answer — whatever they settle on now WINS.
        entry.update(stamp)
        entry["conflict"] = False
        entry["resolved"] = True
        return entry
    if entry["value"] != value:
        entry["conflict"] = True
        entry["pending"] = value
        return entry
    entry["turn"] = turn  # same value repeated — refresh recency
    return entry


def gloss_label(key: str) -> str:
    """How a fact's name reads: the fact's own label, else the built-in one, else the key."""
    from .contract.locale import phrase_or

    return phrase_or(f"evidence.fact_label.{key}", None) or phrase_or(f"evidence.label.{key}", key)


def gloss_value(value: Any, key: str | None = None) -> str:
    """How an evidence value reads: this fact's own wording, else the built-in value wording,
    else the value itself."""
    from .contract.locale import phrase_or

    own = phrase_or(f"evidence.fact_value.{key}.{value}", None) if key else None
    return own or phrase_or(f"evidence.value.{value}", value)


def summary_lt(evidence: dict[str, Any]) -> str:
    """One-line Lithuanian summary for the facts block / solver context /
    ticket ("lemputės: nedega; ar turite kompiuterį: KONFLIKTAS…")."""
    bits = []
    for key, e in evidence.items():
        label = gloss_label(key)
        if e.get("conflict"):
            a = gloss_value(e["value"], key)
            b = gloss_value(e.get("pending"), key)
            from .contract.locale import phrase

            bits.append(phrase("evidence.conflict", label=label, a=a, b=b))
        else:
            bits.append(f"{label}: {gloss_value(e['value'], key)}")
    return "; ".join(bits)


# --- deterministic client-fact extraction (v1) --------------------------------


def _fold(text: str) -> str:
    """Every keyword match here folds BOTH sides (the language's fold), so a
    diacritic STT dropped never hides a fact (live 2026-08-11)."""
    from .contract.locale import lang

    return lang().fold(text)


def _mark_hit(low_folded: str, mark: str) -> bool:
    """Folded substring match with a NEGATION-PREFIX guard: a positive mark
    found only inside a word that itself starts with "ne" is a NO, not a yes
    ("Neniauturiu" — STT of "ne, neturiu" — contains "turiu"; live 2026-08-11
    it landed has_computer=yes while the caller said no). Marks that ARE
    negations ("netur") and multi-word marks skip the guard."""
    m = _fold(mark)
    if m not in low_folded:
        return False
    negation = vocab("negation_prefixes")
    if m.startswith(negation) or " " in m:
        return True
    return any(
        m in tok and not tok.startswith(negation) for tok in low_folded.replace(",", " ").split()
    )


def extract_client_facts(text: str | None) -> dict[str, str]:
    """Keyword-read canonical facts from one caller utterance. Deliberately
    conservative: no match -> no fact (never guesses). Negations first —
    "nedega" contains "dega". All matching on diacritics-folded text."""
    if not text:
        return {}
    low = _fold(text)
    facts: dict[str, str] = {}
    # Negation must attach to the COMPUTER itself: "Neturiu KITO ROUTERIO, tik
    # kompiuterį" is a YES (eval S4 regression: the loose "netur…kompiuter"
    # match read it as no and the solution flipped to ticket instead of bridge).

    from .perceive.detectors import detect_no_device

    if any(w in low for w in vocab("fact_computer_words")):
        if vocab_re("fact_no_computer").search(low):
            facts["has_computer"] = "no"
        elif any(_mark_hit(low, m) for m in vocab("fact_has_computer")) or vocab_re(
            "fact_only_computer"
        ).search(low):
            facts["has_computer"] = "yes"
        elif detect_no_device(low) and not any(w in low for w in vocab("only_words")):
            facts["has_computer"] = "no"
    if any(w in low for w in vocab("fact_lights_words")):
        if any(_fold(m) in low for m in vocab("fact_lights_no")):
            facts["lights"] = "off"
        elif any(w in low for w in vocab("fact_lights_blinking")):
            facts["lights"] = "blinking"
        elif any(_mark_hit(low, m) for m in vocab("fact_lights_yes")):
            facts["lights"] = "on"
    if any(_fold(w) in low for w in vocab("fact_cable_words")):
        if any(_fold(m) in low for m in vocab("fact_cable_out")):
            facts["power_cable"] = "unplugged"
        elif any(_mark_hit(low, m) for m in vocab("fact_cable_in")):
            facts["power_cable"] = "plugged"
    # "razet" — the STT routinely hears "rozetė" as "razetė" (both live calls).
    if any(w in low for w in vocab("fact_outlet_words")) and any(
        m in low for m in vocab("fact_outlet_tried")
    ):
        facts["outlet_works"] = "tried"
    if any(w in low for w in vocab("fact_router_words")) and any(
        _fold(m) in low for m in vocab("fact_device_found")
    ):
        facts["device_present"] = "found"
    # Domain inference: answering about the LIGHTS or the POWER CABLE means the
    # caller is standing AT the device — device_present is implied (eval S4:
    # "nešviečia jokia lemputė" while device_present was still being asked led
    # to a pointless re-ask and a give-up).
    if ("lights" in facts or "power_cable" in facts) and "device_present" not in facts:
        facts["device_present"] = "found"
    return facts


# --- evidence spec (the v2 cards' `needs`, Ledger v2) --------------------------------


def spec_for(verdict: str | None) -> dict[str, Any] | None:
    """What the reading layer needs to understand an answer: the client facts in play, the
    values each can take, and the words that recognise them.

    Wave 3: this comes from the v2 CARDS. `verdict` narrows it to one fault when the case has
    settled on it; otherwise every card's needs are in play, because a caller may answer a
    question before we know which fault it belongs to ("tik viename" is an answer either way).
    """
    from .contract import cards as catalog

    cards = catalog.cards()
    chosen = [cards[verdict]] if verdict in cards else list(cards.values())
    client: dict[str, Any] = {}
    for card in chosen:
        for fact, need in card.needs.items():
            item = client.setdefault(fact, {"answers": {}})
            item["answers"].update(need.answers)
            if need.ask:
                item.setdefault("question_key", need.ask)
            if need.clarify:
                item.setdefault("clarify_key", need.clarify)
            if need.values:
                item.setdefault("value_labels", dict(need.values))
            if need.confirm_values:
                item.setdefault("confirm_values", list(need.confirm_values))
    return {"client": client} if client else None


def fault_need(verdict: str | None) -> str | None:
    """The human wording of WHY a ticket is needed — the card's `escalate.need`."""
    if not verdict:
        return None
    from .contract import cards
    from .contract.locale import maybe_phrase

    card = cards.card(verdict)
    return maybe_phrase(card.escalate.need) if card and card.escalate else None


def _cond_holds(evidence: dict[str, Any], cond: str, confirmed: bool) -> bool:
    cond = cond.strip()
    if cond == "confirmed":
        return confirmed
    if "=" not in cond:
        return False
    key, want = cond.split("=", 1)
    entry = evidence.get(key.strip())
    return entry is not None and not entry.get("conflict") and entry.get("value") == want.strip()


def next_missing(
    evidence: dict[str, Any], spec: dict[str, Any], confirmed: bool
) -> tuple[str, dict[str, Any]] | None:
    """The FIRST evidence key (file order) that is still unknown and whose `kada`
    conditions hold — the next question. None = nothing left to ask."""
    for key, item in (spec.get("client") or {}).items():
        entry = evidence.get(key)
        if entry is not None and not entry.get("conflict"):
            continue  # established (a conflict is settled by the clarify, not here)
        conds = item.get("when") or []
        if all(_cond_holds(evidence, c, confirmed) for c in conds):
            return key, item
    return None


def read_pending_answer(key: str, text: str | None, spec_item: dict | None = None) -> str | None:
    """Interpret a short utterance as the answer to the PENDING evidence key —
    the question context resolves what a bare "Radau." / "Ne" means. UNIVERSAL:
    a card may declare its own `answers: {value: vocabulary}` on a need
    (checked FIRST), so newly added faults get this mechanic by file edit; the
    built-in map covers the piloted keys.
    Matching is diacritics-folded with the negation-prefix guard (_mark_hit)."""
    if not text:
        return None
    low = _fold(text.strip())
    if spec_item:
        for value, name in (spec_item.get("answers") or {}).items():
            marks = vocab(name) if isinstance(name, str) else name
            if isinstance(marks, list | tuple) and any(_mark_hit(low, str(m)) for m in marks):
                return str(value)
    for value, marks in vocab_map("pending_answers").get(key, []):
        if any(_mark_hit(low, m) for m in marks):
            return value
    return None


def polarity(text: str | None) -> str | None:
    """A bare yes/no read for resolving a pending yes/no conflict ("Kaip yra iš
    tiesų?" -> "turiu" / "ne, neturiu"). Negation-prefix aware: a "turiu"
    buried in a "ne…"-word is a NO."""
    if not text:
        return None
    low = _fold(text)
    if any(m in low for m in vocab("polarity_no")):
        return "no"
    if any(_mark_hit(low, m) for m in vocab("polarity_yes")):
        return "yes"
    return None
