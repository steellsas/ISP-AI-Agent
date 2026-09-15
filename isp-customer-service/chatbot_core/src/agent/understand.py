"""SUPRATIMO pass'as — the understanding layer (Ledger v2.5, agreed 2026-08-10).

ONE small-model JSON call per caller turn in the diagnosis stage reads the
reply IN CONTEXT (the pending question, the fault's evidence needs, the ledger,
the last conversation turns) and returns:

    facts       — canonical evidence values it heard (validated against the spec),
    type        — answer | question | deviation | confusion | contradiction,
    understood  — half-sentence of WHAT was understood (the narrator's
                  acknowledgement: "Gerai — routerį radote."),
    confusion   — what exactly the caller did not understand (drives the
                  re-explain-DIFFERENTLY wording),
    confidence  — 0..1.

It is a SENSOR: it never touches state. The ENGINE decides — facts go through
the same set_fact discipline (conflicts, telemetry-over-words), type feeds the
existing routes (side_topic, clarify). Returns None on ANY failure so the
caller falls back to the deterministic keyword extractor — a conversation must
never stall on a model hiccup. Gated by UNDERSTAND=on (config page); unit
tests run with CLASSIFIER=off which disables it too.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .contract import limits

logger = logging.getLogger(__name__)

TURN_TYPES = {"answer", "question", "deviation", "confusion", "contradiction"}

# Canonical values per key — the model may only pick from these (plus omit).
_ALLOWED = {
    "device_present": {"found", "not_found"},
    "lights": {"off", "on", "blinking"},
    "power_cable": {"plugged", "unplugged"},
    "outlet_works": {"tried", "not_working"},
    "has_computer": {"yes", "no"},
    # Bridge phase (2026-08-12): the COMPUTER's network state after the cable
    # was replugged — without this key, "rodo LAN veikia" landed on the ROUTER
    # lights and dragged the call back to a buried hypothesis (live).
    "lan_active": {"active", "inactive"},
}


def perception_model(fallback: str | None) -> str | None:
    """The PERCEPTION-family model (VOICE_PLAN tempo wave): the understand
    pass and the step classifier may run on a FASTER model than the narrator
    (e.g. groq/openai/gpt-oss-120b — Groq inference is ~10x quicker, and the
    perception JSON task is enum-validated, so it degrades safely). Set via
    PERCEPTION_MODEL on the config page; 'default'/empty = the agent model."""
    m = os.getenv("PERCEPTION_MODEL", "").strip()
    return m if m and m != "default" else fallback


def enabled() -> bool:
    if os.getenv("CLASSIFIER", "on").lower() == "off":
        return False  # deterministic test mode — no model calls at all
    return os.getenv("UNDERSTAND", "on").lower() == "on"


def _merged_allowed(extra: dict[str, set[str]] | None) -> dict[str, set[str]]:
    """Built-in keys + whatever the fault's evidence spec declares via
    `answers` (universal: a NEW fault extends the vocabulary by file edit)."""
    merged = {k: set(v) for k, v in _ALLOWED.items()}
    for k, vals in (extra or {}).items():
        merged[k] = merged.get(k, set()) | {str(v) for v in vals}
    return merged


def _system(
    anchor: str,
    needs: str,
    ledger: str,
    allowed_map: dict[str, set[str]],
    step_options: dict[str, str] | None = None,
) -> str:
    """Render the merged perception prompt from prompts/sensors/*.md (R4:
    understanding + step classification in ONE call; R5: instructions live in
    files, code only fills the tokens)."""
    from .prompts import load_node_prompt

    allowed = "; ".join(f"{k}: {sorted(v)}" for k, v in allowed_map.items())
    step_json = ""
    step_rules = ""
    if step_options:
        opts = "\n".join(f'    - "{k}": {v}' for k, v in step_options.items())
        step_json = (
            ', "step": {"label": "...", "is_answer": bool, '
            '"internally_inconsistent": bool, "confidence": 0.0-1.0}'
        )
        step_rules = load_node_prompt("sensors/perception_step").replace("<<options>>", opts)
    return (
        load_node_prompt("sensors/perception")
        .replace("<<anchor>>", anchor)
        .replace("<<needs>>", needs)
        .replace("<<ledger>>", ledger or "(nieko)")
        .replace("<<allowed>>", allowed)
        .replace("<<step_json>>", step_json)
        .replace("<<step_rules>>", step_rules)
        .strip()
    )


def understand(
    utterance: str,
    *,
    anchor: str,
    needs: str,
    ledger_summary: str,
    history_tail: list[dict[str, str]] | None = None,
    model: str | None = None,
    allowed_extra: dict[str, set[str]] | None = None,
    step_options: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Read one caller turn. None on any failure -> keyword fallback.

    R4 perception merge: when `step_options` is given (an asked CONFIRM/INSTRUCT
    step awaits its answer), the SAME call also classifies the reply against the
    step's routing keys — the result rides back as `step` and replaces the
    separate classifier.classify_step call (one LLM round-trip fewer per turn).
    """
    if not utterance or not utterance.strip():
        return None
    allowed_map = _merged_allowed(allowed_extra)
    try:
        from src.services.llm.client import llm_json_completion

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": _system(anchor, needs, ledger_summary, allowed_map, step_options),
            }
        ]
        for m in (history_tail or [])[-limits.get("understand_history_messages") :]:
            role = "assistant" if m.get("role") == "assistant" else "user"
            content = (m.get("content") or "")[:200]
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": utterance[:400]})
        data = llm_json_completion(messages=messages, model=perception_model(model))
        if not isinstance(data, dict):
            return None
        turn_type = str(data.get("type") or "answer").lower()
        if turn_type not in TURN_TYPES:
            turn_type = "answer"
        raw_facts = data.get("facts")
        facts: dict[str, str] = {}
        if isinstance(raw_facts, dict):
            for k, v in raw_facts.items():
                if k in allowed_map and str(v) in allowed_map[k]:
                    facts[k] = str(v)
        confidence = float(data.get("confidence") or 0.5)
        # Hallucination guards (live 2026-08-10: "Galim patikrinti, ką man
        # reikia daryti?" came back with FIVE facts the caller never said,
        # poisoning the ledger and forcing two phantom clarifies):
        # a question/confusion does not STATE facts, and low-confidence facts
        # are worse than no facts — the deterministic layers cover the gap.
        if turn_type not in ("answer", "contradiction") or confidence < limits.get(
            "understand_facts_min_confidence"
        ):
            facts = {}
        # Merged step classification (R4): validated exactly like the standalone
        # classifier — unknown labels are dropped so the walker falls back.
        step: dict[str, Any] | None = None
        raw_step = data.get("step")
        if step_options and isinstance(raw_step, dict):
            label = str(raw_step.get("label") or "unclear")
            if label in set(step_options) | {"unclear"}:
                step = {
                    "label": label,
                    "is_answer": bool(raw_step.get("is_answer", True)),
                    "internally_inconsistent": bool(raw_step.get("internally_inconsistent", False)),
                    "confidence": max(0.0, min(1.0, float(raw_step.get("confidence") or 0.5))),
                }
        return {
            "facts": facts,
            "type": turn_type,
            "understood": str(data.get("understood") or "")[:200],
            "confusion": str(data.get("confusion") or "")[:200],
            "confidence": confidence,
            "step": step,
        }
    except Exception as e:  # any failure -> deterministic fallback
        logger.warning(f"understand pass failed: {e}")
        return None


def understand_ticket(
    utterance: str, *, stage: str, anchor: str, model: str | None = None
) -> dict[str, Any] | None:
    """Read one TICKET-DIALOGUE answer (stage: 'phone' | 'hours') in context —
    predicting caller phrasing is impossible ("Bet kada galima per pietus iš
    ryto" is an HOURS answer, not a question). Returns
    {"value": str|None, "type": "answer|question|refusal|other"};
    None on any failure -> the keyword logic decides as before."""
    if not utterance or not utterance.strip() or stage not in ("phone", "hours"):
        return None
    from .prompts import load_node_prompt

    task = load_node_prompt(f"sensors/ticket_reader_{stage}")
    system = (
        load_node_prompt("sensors/ticket_reader")
        .replace("<<anchor>>", anchor)
        .replace("<<task>>", task)
    )
    try:
        from src.services.llm.client import llm_json_completion

        data = llm_json_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": utterance[:300]},
            ],
            model=perception_model(model),
        )
        if not isinstance(data, dict):
            return None
        answer_type = str(data.get("type") or "other").lower()
        if answer_type not in ("answer", "question", "refusal", "other"):
            answer_type = "other"
        value = data.get("value")
        value = str(value)[:80].strip() if value not in (None, "", "null") else None
        return {"value": value, "type": answer_type}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"understand_ticket failed: {e}")
        return None
