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

_NEG_LIGHTS = ("nedega", "ne dega", "nei viena", "nė viena", "ne viena", "jokia lemp", "nešvie")
_POS_LIGHTS = ("dega", "šviečia", "sviecia", "žiba", "ziba")
_HAS_PC = ("turiu kompiuter", "yra kompiuter", "turim kompiuter", "kompiuteris yra", "turiu pc")
_CABLE_WORDS = ("laid", "kabel", "maitinim")
_CABLE_IN = ("įkišt", "ikist", "įkišau", "ikisau", "pajungt", "prijungt", "gerai įkiš", "abiejuose")
_CABLE_OUT = ("nepajungt", "neprijungt", "atjungt", "ištraukt", "istraukt", "iškrit", "iskrit")


def extract_client_facts(text: str | None) -> dict[str, str]:
    """Keyword-read canonical facts from one caller utterance. Deliberately
    conservative: no match -> no fact (never guesses). Negations first —
    "nedega" contains "dega"."""
    if not text:
        return {}
    low = text.lower()
    facts: dict[str, str] = {}
    from .resolution import detect_no_device

    # Negation FIRST — "neturiu kompiuterio" contains "turiu kompiuter".
    if "kompiuter" in low and detect_no_device(low):
        facts["has_computer"] = "no"
    elif any(m in low for m in _HAS_PC):
        facts["has_computer"] = "yes"
    if "lemp" in low or "šviesel" in low or "sviesel" in low:
        if any(m in low for m in _NEG_LIGHTS):
            facts["lights"] = "nedega"
        elif "mirksi" in low or "mirkčioja" in low:
            facts["lights"] = "mirksi"
        elif any(m in low for m in _POS_LIGHTS):
            facts["lights"] = "dega"
    if any(w in low for w in _CABLE_WORDS):
        if any(m in low for m in _CABLE_OUT):
            facts["power_cable"] = "atjungtas"
        elif any(m in low for m in _CABLE_IN):
            facts["power_cable"] = "įkištas"
    if "rozet" in low and any(m in low for m in ("kit", "band", "perjung")):
        facts["outlet_works"] = "bandyta"
    if ("router" in low or "dėžut" in low or "dezut" in low) and any(
        m in low for m in ("radau", "priėjau", "priejau", "matau", "esu prie", "suradau")
    ):
        facts["device_present"] = "rado"
    return facts


def polarity(text: str | None) -> str | None:
    """A bare yes/no read for resolving a pending yes/no conflict ("Kaip yra iš
    tiesų?" -> "turiu" / "ne, neturiu")."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in ("netur", "neturi", "ne,", "ne ", "nėra", "nera")):
        return "no"
    if any(m in low for m in ("turiu", "turim", "taip", "yra")):
        return "yes"
    return None
