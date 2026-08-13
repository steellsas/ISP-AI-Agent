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

TELEMETRY = "telemetry"
CLIENT = "client"

# Canonical client-side evidence keys for the piloted fault (no_mac_observed).
# Values are canonical strings so conflicts are detectable; labels feed the
# clarify phrase and the ticket summary.
LABELS = {
    "has_computer": "ar turite kompiuterį",
    "lights": "routerio lemputės",
    "power_cable": "maitinimo laidas",
    "outlet_works": "rozetė",
    "device_present": "routeris surastas",
    "lan_active": "kompiuterio LAN ryšys",
    "verdict": "telemetrijos diagnozė",
    "side": "gedimo pusė",
}

VALUE_LT = {
    "yes": "turite",
    "no": "neturite",
    "nedega": "nedega",
    "dega": "dega",
    "mirksi": "mirksi",
    "įkištas": "įkištas",
    "atjungtas": "atjungtas",
    "bandyta": "bandyta",
    "rado": "rado",
    "aktyvus": "aktyvus",
    "neaktyvus": "neaktyvus",
}


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


def summary_lt(evidence: dict[str, Any]) -> str:
    """One-line Lithuanian summary for the facts block / solver context /
    ticket ("lemputės: nedega; ar turite kompiuterį: KONFLIKTAS…")."""
    bits = []
    for key, e in evidence.items():
        label = LABELS.get(key, key)
        if e.get("conflict"):
            a = VALUE_LT.get(e["value"], e["value"])
            b = VALUE_LT.get(e.get("pending"), e.get("pending"))
            bits.append(f"{label}: KONFLIKTAS ({a} ↔ {b})")
        else:
            bits.append(f"{label}: {VALUE_LT.get(e['value'], e['value'])}")
    return "; ".join(bits)


# --- deterministic client-fact extraction (v1) --------------------------------

# STT routinely drops Lithuanian diacritics ("Tai ikištas", "razetė") — every
# keyword match here folds BOTH sides so a dropped nosinė never hides a fact
# (live 2026-08-11: "įkištas" heard without į failed the flip corroboration).
_FOLD = str.maketrans("ąčęėįšųūž", "aceeisuuz")


def _fold(text: str) -> str:
    return text.lower().translate(_FOLD)


def _mark_hit(low_folded: str, mark: str) -> bool:
    """Folded substring match with a NEGATION-PREFIX guard: a positive mark
    found only inside a word that itself starts with "ne" is a NO, not a yes
    ("Neniauturiu" — STT of "ne, neturiu" — contains "turiu"; live 2026-08-11
    it landed has_computer=yes while the caller said no). Marks that ARE
    negations ("netur") and multi-word marks skip the guard."""
    m = _fold(mark)
    if m not in low_folded:
        return False
    if m.startswith("ne") or " " in m:
        return True
    return any(
        m in tok and not tok.startswith("ne") for tok in low_folded.replace(",", " ").split()
    )


_NEG_LIGHTS = ("nedega", "ne dega", "nei viena", "nė viena", "ne viena", "jokia lemp", "nešvie")
_POS_LIGHTS = ("dega", "šviečia", "sviecia", "žiba", "ziba")
_HAS_PC = ("turiu kompiuter", "yra kompiuter", "turim kompiuter", "kompiuteris yra", "turiu pc")
_CABLE_WORDS = ("laid", "kabel", "maitinim")
_CABLE_IN = ("įkišt", "ikist", "įkišau", "ikisau", "pajungt", "prijungt", "gerai įkiš", "abiejuose")
_CABLE_OUT = ("nepajungt", "neprijungt", "atjungt", "ištraukt", "istraukt", "iškrit", "iskrit")


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
    import re as _re

    from .resolution import detect_no_device

    if "kompiuter" in low:
        if _re.search(r"(netur\w*|nera)\s+(?:\w+\s+){0,2}kompiuter", low):
            facts["has_computer"] = "no"
        elif any(_mark_hit(low, m) for m in _HAS_PC) or _re.search(r"tik\s+(su\s+)?kompiuter", low):
            facts["has_computer"] = "yes"
        elif detect_no_device(low) and "tik" not in low:
            facts["has_computer"] = "no"
    if "lemp" in low or "sviesel" in low:
        if any(_fold(m) in low for m in _NEG_LIGHTS):
            facts["lights"] = "nedega"
        elif "mirksi" in low or "mirkcioja" in low:
            facts["lights"] = "mirksi"
        elif any(_mark_hit(low, m) for m in _POS_LIGHTS):
            facts["lights"] = "dega"
    if any(_fold(w) in low for w in _CABLE_WORDS):
        if any(_fold(m) in low for m in _CABLE_OUT):
            facts["power_cable"] = "atjungtas"
        elif any(_mark_hit(low, m) for m in _CABLE_IN):
            facts["power_cable"] = "įkištas"
    # "razet" — the STT routinely hears "rozetė" as "razetė" (both live calls).
    if ("rozet" in low or "razet" in low) and any(m in low for m in ("kit", "band", "perjung")):
        facts["outlet_works"] = "bandyta"
    if ("router" in low or "dezut" in low) and any(
        _fold(m) in low for m in ("radau", "priėjau", "matau", "esu prie", "suradau")
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
    """The fault's evidence spec from faults.yaml ({client, patvirtinta_kai,
    paneigta_kai, paneigta_veda}), or None when the fault declares none
    (fail-soft: the walker/solver flow runs as before)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    if not isinstance(fault, dict):
        return None
    spec = fault.get("evidence")
    return spec if isinstance(spec, dict) and isinstance(spec.get("client"), dict) else None


def fault_isvada(verdict: str | None) -> str | None:
    """How to ANNOUNCE the confirmed hypothesis ("Panašu — {isvada}") —
    `isvada:` in faults.yaml; falls back to `reikalinga`."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    if not isinstance(fault, dict):
        return None
    return str(fault.get("isvada") or fault.get("reikalinga") or "") or None


def solution_descriptions(verdict: str | None) -> list[str]:
    """Human wording of the declared solutions (`aprasymas` on each sprendimai
    entry; the bare `tada` key as fallback) — feeds the findings announce."""
    if not verdict:
        return []
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("sprendimai") if isinstance(fault, dict) else None
    out = []
    for rule in rules or []:
        if isinstance(rule, dict):
            out.append(str(rule.get("aprasymas") or rule.get("tada") or "").strip())
    return [x for x in out if x]


def client_facts_lt(evidence: dict[str, Any]) -> str:
    """Only the CLIENT-established, conflict-free facts, human-worded — the
    "ką patikrinome kartu" part of the findings announce."""
    bits = []
    for key, e in evidence.items():
        if e.get("source") == CLIENT and not e.get("conflict") and e.get("value") != "neaišku":
            bits.append(f"{LABELS.get(key, key)}: {VALUE_LT.get(e['value'], e['value'])}")
    return "; ".join(bits)


def fault_bridge_fail(verdict: str | None) -> dict[str, str]:
    """The fault's declared bridge-failure texts (`tiltas_nepavyko:` in
    faults.yaml): `pastaba` spoken to the caller before the technician
    registration, `prierasas` appended to the ticket details."""
    if not verdict:
        return {}
    from .faults import _faults

    fault = _faults().get(verdict)
    d = fault.get("tiltas_nepavyko") if isinstance(fault, dict) else None
    return d if isinstance(d, dict) else {}


def fault_need(verdict: str | None) -> str | None:
    """The human wording of WHY a ticket is needed (`reikalinga:` in the file)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    need = fault.get("reikalinga") if isinstance(fault, dict) else None
    return str(need) if need else None


def _cond_holds(evidence: dict[str, Any], cond: str, confirmed: bool) -> bool:
    cond = cond.strip()
    if cond == "patvirtinta":
        return confirmed
    if "=" not in cond:
        return False
    key, want = cond.split("=", 1)
    entry = evidence.get(key.strip())
    return entry is not None and not entry.get("conflict") and entry.get("value") == want.strip()


def hypothesis_status(evidence: dict[str, Any], spec: dict[str, Any]) -> str | None:
    """'confirmed' when ALL patvirtinta_kai hold, 'refuted' when ANY paneigta_kai
    holds, else None (still collecting). Refute wins — a lit lamp disproves the
    dead-router path no matter what else was gathered."""
    if any(_cond_holds(evidence, c, False) for c in (spec.get("paneigta_kai") or [])):
        return "refuted"
    confirm = spec.get("patvirtinta_kai")
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
        conds = item.get("kada") or []
        if all(_cond_holds(evidence, c, confirmed) for c in conds):
            return key, item
    return None


def solution_for(evidence: dict[str, Any], verdict: str | None) -> str | None:
    """The declared solution ('bridge' / 'ticket') whose `jei` conditions hold."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("sprendimai") if isinstance(fault, dict) else None
    for rule in rules or []:
        if isinstance(rule, dict) and all(
            _cond_holds(evidence, c, True) for c in (rule.get("jei") or [])
        ):
            return rule.get("tada")
    return None


def solution_step(evidence: dict[str, Any], verdict: str | None) -> str | None:
    """The walker STEP declared on the matching sprendimai rule (`zingsnis` in
    faults.yaml) — where the flow RESUMES if the solver is benched
    mid-solution (live 2026-08-11: a bailout landed on a long-stale dr_intro
    and improvised into a ticket one step from a working bridge)."""
    if not verdict:
        return None
    from .faults import _faults

    fault = _faults().get(verdict)
    rules = fault.get("sprendimai") if isinstance(fault, dict) else None
    for rule in rules or []:
        if isinstance(rule, dict) and all(
            _cond_holds(evidence, c, True) for c in (rule.get("jei") or [])
        ):
            return rule.get("zingsnis")
    return None


# Context reads for the JUST-ASKED evidence key (2026-08-10): a bare "Radau."
# to "Radote?" carries no noun, so the general extractor (which demands one)
# finds nothing — and a clear answer became a give-up. When the engine knows
# WHICH question is pending, short answers read against THAT key only.
_PENDING_ANSWERS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "device_present": [
        (
            "rado",
            (
                "radau",
                "radome",
                "suradau",
                "taip",
                "yra",
                "matau",
                "priėjau",
                "priejau",
                "stoviu prie",
            ),
        ),
    ],
    "lights": [
        # Negation first — "nedega" contains "dega".
        (
            "nedega",
            (
                "nedega",
                "ne dega",
                "nešvie",
                "nesvie",
                "jokia",
                "nė viena",
                "ne viena",
                "ne,",
                "ne ",
            ),
        ),
        ("mirksi", ("mirksi", "mirkčioja", "mirkcioja")),
        ("dega", ("dega", "šviečia", "sviecia", "taip")),
    ],
    "power_cable": [
        ("atjungtas", ("atjungt", "ištraukt", "istraukt", "nepajungt", "ne,", "ne ")),
        ("įkištas", ("įkišt", "ikist", "pajungt", "prijungt", "gerai", "taip", "tvirtai")),
    ],
    "outlet_works": [
        ("bandyta", ("bandž", "bandz", "band", "taip", "kita", "veikia", "perjung")),
    ],
    "has_computer": [
        ("no", ("netur", "nėra", "nera", "ne,", "ne ")),
        ("yes", ("turiu", "turim", "taip", "yra")),
    ],
    "lan_active": [
        ("neaktyvus", ("neaktyv", "nedega", "nerodo", "nėra", "nera", "ne,", "ne ")),
        ("aktyvus", ("aktyv", "veikia", "dega", "rodo", "taip", "yra")),
    ],
}


def read_pending_answer(key: str, text: str | None, spec_item: dict | None = None) -> str | None:
    """Interpret a short utterance as the answer to the PENDING evidence key —
    the question context resolves what a bare "Radau." / "Ne" means. UNIVERSAL:
    a fault may declare its own `atsakymai: {reikšmė: [požymiai]}` on the
    evidence item in faults.yaml (checked FIRST), so newly added faults get
    this mechanic by file edit; the built-in map covers the piloted keys.
    Matching is diacritics-folded with the negation-prefix guard (_mark_hit)."""
    if not text:
        return None
    low = _fold(text.strip())
    if spec_item:
        for value, marks in (spec_item.get("atsakymai") or {}).items():
            if isinstance(marks, list | tuple) and any(_mark_hit(low, str(m)) for m in marks):
                return str(value)
    for value, marks in _PENDING_ANSWERS.get(key, []):
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
    if any(m in low for m in ("netur", "ne,", "ne ", "nera")):
        return "no"
    if any(_mark_hit(low, m) for m in ("turiu", "turim", "taip", "yra")):
        return "yes"
    return None
