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

from typing import Any

from pydantic import BaseModel

from .contract.locale import vocab, vocab_map, vocab_re

TELEMETRY = "telemetry"


class EvidenceConflict(BaseModel):
    """A client fact contradicted an earlier client value: one scripted clarify
    ("sakėte X, dabar Y — kaip yra iš tiesų?") is due for `key`."""

    key: str
    old: str
    new: str


class FactConfirm(BaseModel):
    """A story-flipping volunteered fact parked for one confirm question before
    it may enter the ledger."""

    key: str
    value: str


CLIENT = "client"


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
    if entry["value"] == "neaišku":
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


def _pack_glosses() -> tuple[dict[str, str], dict[str, str]]:
    """Pack-declared Lithuanian glosses merged over every loaded fault:
    per-fact `label:` and per-value `reiksmes:` — so a NEW pack's facts read
    human ('routerio keitimas: keitė įrangą'), never as raw English keys
    (live 2026-08-13: the recap spoke 'changed_device: keite')."""
    labels: dict[str, str] = {}
    values: dict[str, str] = {}
    try:
        from .contract.locale import phrase
        from .faults import _faults

        for spec in _faults().values():
            client = (
                ((spec or {}).get("evidence") or {}).get("client")
                if isinstance(spec, dict)
                else None
            )
            for key, item in (client or {}).items():
                if isinstance(item, dict):
                    if item.get("label_key"):
                        labels[str(key)] = phrase(item["label_key"])
                    for v, gloss in (item.get("value_label_keys") or {}).items():
                        values[str(v)] = phrase(gloss)
    except Exception:  # pragma: no cover - glosses are cosmetic, never break
        pass
    return labels, values


def gloss_label(key: str) -> str:
    labels, _ = _pack_glosses()
    from .contract.locale import phrase_or

    return labels.get(key) or phrase_or(f"evidence.label.{key}", key)


def gloss_value(value: Any) -> str:
    _, values = _pack_glosses()
    from .contract.locale import phrase_or

    return values.get(value) or phrase_or(f"evidence.value.{value}", value)


def summary_lt(evidence: dict[str, Any]) -> str:
    """One-line Lithuanian summary for the facts block / solver context /
    ticket ("lemputės: nedega; ar turite kompiuterį: KONFLIKTAS…")."""
    bits = []
    for key, e in evidence.items():
        label = gloss_label(key)
        if e.get("conflict"):
            a = gloss_value(e["value"])
            b = gloss_value(e.get("pending"))
            from .contract.locale import phrase

            bits.append(phrase("evidence.conflict", label=label, a=a, b=b))
        else:
            bits.append(f"{label}: {gloss_value(e['value'])}")
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

    from .resolution import detect_no_device

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
            facts["lights"] = "nedega"
        elif any(w in low for w in vocab("fact_lights_blinking")):
            facts["lights"] = "mirksi"
        elif any(_mark_hit(low, m) for m in vocab("fact_lights_yes")):
            facts["lights"] = "dega"
    if any(_fold(w) in low for w in vocab("fact_cable_words")):
        if any(_fold(m) in low for m in vocab("fact_cable_out")):
            facts["power_cable"] = "atjungtas"
        elif any(_mark_hit(low, m) for m in vocab("fact_cable_in")):
            facts["power_cable"] = "įkištas"
    # "razet" — the STT routinely hears "rozetė" as "razetė" (both live calls).
    if any(w in low for w in vocab("fact_outlet_words")) and any(
        m in low for m in vocab("fact_outlet_tried")
    ):
        facts["outlet_works"] = "bandyta"
    if any(w in low for w in vocab("fact_router_words")) and any(
        _fold(m) in low for m in vocab("fact_device_found")
    ):
        facts["device_present"] = "rado"
    # Domain inference: answering about the LIGHTS or the POWER CABLE means the
    # caller is standing AT the device — device_present is implied (eval S4:
    # "nešviečia jokia lemputė" while device_present was still being asked led
    # to a pointless re-ask and a give-up).
    if ("lights" in facts or "power_cable" in facts) and "device_present" not in facts:
        facts["device_present"] = "rado"
    return facts


# --- evidence spec (faults.yaml `evidence:` block, Ledger v2) -----------------


def spec_for(verdict: str | None) -> dict[str, Any] | None:
    """The fault's evidence spec from faults.yaml ({client, confirmed_when,
    refuted_when, on_refuted}), or None when the fault declares none
    (fail-soft: the walker/solver flow runs as before)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    if not isinstance(fault, dict):
        return None
    spec = fault.get("evidence")
    return spec if isinstance(spec, dict) and isinstance(spec.get("client"), dict) else None


def fault_conclusion(verdict: str | None) -> str | None:
    """How to ANNOUNCE the confirmed hypothesis ("Panašu — {isvada}") —
    `conclusion_key:` in the pack; falls back to `ticket_need_key`."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    if not isinstance(fault, dict):
        return None
    from .contract.locale import maybe_phrase

    return maybe_phrase(fault.get("conclusion_key") or fault.get("ticket_need_key"))


def fault_offer_goal(verdict: str | None) -> str | None:
    """The fault's OWN findings-moment offer script (`offer_goal:` in the pack) —
    ticket-first faults use it to frame the primary outcome (the technician)
    before the optional convenience (the bridge). None -> the generic
    'Pasiūlyk pasirinkimą (A ARBA B)' framing."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    if not isinstance(fault, dict):
        return None
    return str(fault.get("offer_goal") or "") or None


def open_goals_lt(evidence: dict[str, Any], verdict: str | None) -> str:
    """The still-open goals (`reikia`) whose `kada` gates hold — the narrator's
    situational awareness: what this conversation still has to establish.
    Mirrors next_missing's eligibility so the list never names a question the
    drive would not ask."""
    spec = spec_for(verdict)
    if not spec:
        return ""
    confirmed = hypothesis_status(evidence, spec) == "confirmed"
    goals = []
    for key, item in (spec.get("client") or {}).items():
        entry = evidence.get(key)
        if entry is not None and not entry.get("conflict"):
            continue
        if not all(_cond_holds(evidence, c, confirmed) for c in item.get("when") or []):
            continue
        if item.get("goal"):
            goals.append(str(item["goal"]))
    return "; ".join(goals)


def solution_descriptions(verdict: str | None) -> list[str]:
    """Human wording of the declared solutions (`description_key` on each solutions
    entry; the bare `action` as fallback) — feeds the findings announce."""
    if not verdict:
        return []
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("solutions") if isinstance(fault, dict) else None
    from .contract.locale import maybe_phrase

    out = []
    for rule in rules or []:
        if isinstance(rule, dict):
            out.append(
                str(maybe_phrase(rule.get("description_key")) or rule.get("action") or "").strip()
            )
    return [x for x in out if x]


def client_facts_lt(evidence: dict[str, Any]) -> str:
    """Only the CLIENT-established, conflict-free facts, human-worded — the
    "ką patikrinome kartu" part of the findings announce."""
    bits = []
    for key, e in evidence.items():
        if e.get("source") == CLIENT and not e.get("conflict") and e.get("value") != "neaišku":
            bits.append(f"{gloss_label(key)}: {gloss_value(e['value'])}")
    return "; ".join(bits)


def fault_bridge_fail(verdict: str | None) -> dict[str, str]:
    """The fault's declared bridge-failure texts (`bridge_failed:` in
    faults.yaml): `pastaba` spoken to the caller before the technician
    registration, `prierasas` appended to the ticket details."""
    if not verdict:
        return {}
    from .faults import _faults

    fault = _faults().get(verdict)
    d = fault.get("bridge_failed") if isinstance(fault, dict) else None
    if not isinstance(d, dict):
        return {}
    from .contract.locale import template

    # Templates: the ticket note carries a {lan} placeholder the caller fills.
    return {
        "notice": template(d["notice_key"]),
        "ticket_note": template(d["ticket_note_key"]),
    }


def fault_need(verdict: str | None) -> str | None:
    """The human wording of WHY a ticket is needed (`ticket_need_key:` in the pack)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    from .contract.locale import maybe_phrase

    return maybe_phrase(fault.get("ticket_need_key")) if isinstance(fault, dict) else None


def _cond_holds(evidence: dict[str, Any], cond: str, confirmed: bool) -> bool:
    cond = cond.strip()
    if cond == "confirmed":
        return confirmed
    if "=" not in cond:
        return False
    key, want = cond.split("=", 1)
    entry = evidence.get(key.strip())
    return entry is not None and not entry.get("conflict") and entry.get("value") == want.strip()


def hypothesis_status(evidence: dict[str, Any], spec: dict[str, Any]) -> str | None:
    """'confirmed' when ALL confirmed_when hold, 'refuted' when ANY refuted_when
    holds, else None (still collecting). Refute wins — a lit lamp disproves the
    dead-router path no matter what else was gathered."""
    if any(_cond_holds(evidence, c, False) for c in (spec.get("refuted_when") or [])):
        return "refuted"
    confirm = spec.get("confirmed_when")
    # An EXPLICIT empty list means "confirmed by telemetry from the start" —
    # the client facts pick the SOLUTION, not the hypothesis (R4b packs:
    # foreign_mac, healthy_to_router). An ABSENT key keeps the old meaning
    # (no confirmation logic declared -> still collecting).
    if isinstance(confirm, list) and not confirm:
        return "confirmed"
    if confirm and all(_cond_holds(evidence, c, False) for c in confirm):
        return "confirmed"
    return None


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


def solution_for(evidence: dict[str, Any], verdict: str | None) -> str | None:
    """The declared solution ('bridge' / 'ticket') whose `jei` conditions hold."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("solutions") if isinstance(fault, dict) else None
    for rule in rules or []:
        if isinstance(rule, dict) and all(
            _cond_holds(evidence, c, True) for c in (rule.get("when") or [])
        ):
            return rule.get("action")
    return None


def solution_step(evidence: dict[str, Any], verdict: str | None) -> str | None:
    """The walker STEP declared on the matching solutions rule (`step_role` in
    faults.yaml) — where the flow RESUMES if the solver is benched
    mid-solution (live 2026-08-11: a bailout landed on a long-stale dr_intro
    and improvised into a ticket one step from a working bridge)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("solutions") if isinstance(fault, dict) else None
    for rule in rules or []:
        if isinstance(rule, dict) and all(
            _cond_holds(evidence, c, True) for c in (rule.get("when") or [])
        ):
            from .faults import step_by_role

            step = step_by_role(verdict, rule.get("step_role") or "")
            return step.id if step else None
    return None


def read_pending_answer(key: str, text: str | None, spec_item: dict | None = None) -> str | None:
    """Interpret a short utterance as the answer to the PENDING evidence key —
    the question context resolves what a bare "Radau." / "Ne" means. UNIVERSAL:
    a fault may declare its own `answers: {value: [markers]}` on the
    evidence item in faults.yaml (checked FIRST), so newly added faults get
    this mechanic by file edit; the built-in map covers the piloted keys.
    Matching is diacritics-folded with the negation-prefix guard (_mark_hit)."""
    if not text:
        return None
    low = _fold(text.strip())
    if spec_item:
        for value, marks in (spec_item.get("answers") or {}).items():
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
