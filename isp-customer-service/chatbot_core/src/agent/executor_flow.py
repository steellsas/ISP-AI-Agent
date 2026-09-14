"""
Executor flow — the ONLY place tools run and tickets are registered.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent —
the deterministic tool-access gate, the gated tool-call loop, the STATE-driven
idempotent ticket registration and the demo bridge simulation. Functions take
(state, rt) — the call state and the AgentRuntime. tools run through rt.tools (the
gateway).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .dialog_utils import assistant_tool_message
from .trace import tools_called_this_session, trace_note

logger = logging.getLogger(__name__)


def execute_tool_calls(state: Any, rt: Any, message: Any) -> list[dict]:
    """Echo the assistant tool-call message, run each tool through the gate,
    append results to history, trace, and update state. Returns the executed
    list."""
    from .narrator_flow import augment_tool_result

    state.messages.append(assistant_tool_message(message))
    executed = []
    for tc in message.tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.warning(f"[AGENT] Bad tool arguments for {name}: {raw_args!r}")
            trace_note(rt.tracer, state, "tool_args", f"{name}: bad JSON args {raw_args!r}")
            args = {}

        logger.info(f"[AGENT] Tool call: {name}")
        # The gateway commits state BEFORE augmenting: resolve_address sets
        # customer_id there, and the augment then diagnoses in the same turn (it
        # read a not-yet-committed id and skipped, so the strategy never
        # activated). The state update reads only raw tool fields, never the ones
        # augment adds, so the order is safe.
        result = rt.tools.run(state, rt, name, args, reason="llm")
        observation = result.observation
        if not result.gated:
            observation = augment_tool_result(state, rt, name, observation)

        state.messages.append({"role": "tool", "tool_call_id": tc.id, "content": observation})
        state.intake.observations.append(observation)
        executed.append({"name": name, "arguments": args, "observation": observation})
    return executed


def register_ticket_from_state(state: Any, rt: Any, step_id: str | None) -> None:
    """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
    cause from the hypothesis/verdict, actions from this call's trace — never from
    the model's free text (which once invented an invalid ticket_type). Idempotent:
    an existing ticket is never duplicated. Best-effort: a failure is traced and the
    close still proceeds (the call record keeps the outcome)."""
    from .glossary import DIAGNOSIS_LT, TICKET_NEED_LT

    s = state
    if s.ticket.ticket_id or not s.identity.customer_id:
        return
    cause = (
        (s.diagnosis.hypothesis or {}).get("cause")
        or (s.resolution.procedure or {}).get("verdict")
        or ""
    )
    gloss = DIAGNOSIS_LT.get(cause, cause or "nenustatyta")
    details = f"Gedimas: {s.intake.problem_type or 'internetas'} — {gloss}."
    need = TICKET_NEED_LT.get(cause)
    if need:
        # Sentence-cased as its own sentence — "Reikalinga: reikalingas…" doubled up.
        details += f" {need[0].upper()}{need[1:]}."
    # Bridge attempt outcome (2026-08-12): the technician reads WHAT was
    # already tried — "pajungti PC nepavyko (LAN aktyvus)" changes what
    # they bring and check first.
    if state.ticket.bridge_fail_note:
        details += f" {state.ticket.bridge_fail_note}"
    # Contacts from the ticket dialogue (2026-08-04): who to reach and when.
    if s.ticket.contact_phone or s.identity.caller_name:
        kas = s.identity.caller_name or "skambinęs asmuo"
        rel = f" ({s.identity.caller_relation})" if s.identity.caller_relation else ""
        details += (
            f" Kontaktas: {kas}{rel}, tel. {s.ticket.contact_phone or s.identity.caller_phone}"
        )
        if s.ticket.contact_hours:
            details += f", skambinti: {s.ticket.contact_hours}"
        details += "."
    # The caller's anamnesis rides on the ticket — the human sees WHEN it broke
    # and after what, not just the telemetry verdict (Step 2 analysis).
    if s.intake.anamnesis_when or s.intake.anamnesis_trigger or s.intake.anamnesis_raw:
        bits = []
        if s.intake.anamnesis_when:
            bits.append(f"dingo {s.intake.anamnesis_when}")
        if s.intake.anamnesis_trigger:
            bits.append(f"po: {s.intake.anamnesis_trigger}")
        details += f" Klientas: {', '.join(bits) if bits else s.intake.anamnesis_raw}."
    if step_id == "dr_register_router":
        details += " Laikinas tiltas per kompiuterį veikia; routeris sugedęs, reikia keisti."
    # Ledger: what the CALLER established (client-side evidence) — the human
    # taking over sees the checked physical facts, not just telemetry.
    client_bits = []
    from .evidence import CLIENT as _EV_CLIENT
    from .evidence import LABELS as _EV_LABELS
    from .evidence import VALUE_LT as _EV_VALUES

    for key, e in s.diagnosis.evidence.items():
        if e.get("source") == _EV_CLIENT and not e.get("conflict"):
            client_bits.append(
                f"{_EV_LABELS.get(key, key)}: {_EV_VALUES.get(e['value'], e['value'])}"
            )
    if client_bits:
        details += f" Patikrinta su klientu: {'; '.join(client_bits)}."
    # Why it was not solved (refusal / demand / not home) — recorded on the ticket
    # so the technician knows the context (policy 2026-07-30).
    reason_note = (s.resolution.procedure or {}).get("escalate_reason")
    if reason_note:
        details += f" {reason_note}"
    # What was already TRIED and ruled out — the human taking over must not redo
    # it (after-hours philosophy 2026-08-03: the agent attempts, a person takes
    # over via the ticket with the full attempt history).
    tried = list(s.diagnosis.failed_hypotheses) + [
        x.get("cause") for x in s.diagnosis.rejected_hypotheses if x.get("cause")
    ]
    if tried:
        glosses = ", ".join(DIAGNOSIS_LT.get(c, c) for c in dict.fromkeys(tried))
        details += f" Bandyta/atmesta: {glosses}."
    # A (2026-08-21): secondary problems the caller mentioned mid-call — the
    # technician checks them on the same visit.
    if getattr(s.intake, "secondary_problems", None):
        extra = "; ".join(f"{x['tipas']}: „{x['tekstas']}“" for x in s.intake.secondary_problems)
        details += f" Papildomai patikrinti: {extra}."
    actions = tools_called_this_session(rt.tracer)
    args = {
        "customer_id": s.identity.customer_id,
        "problem_type": "technician_visit",
        "problem_description": details,
        "priority": "high",
        "notes": ("Atlikta: " + ", ".join(actions)) if actions else "",
    }
    try:
        # The state update sets ticket_id.
        rt.tools.run(state, rt, "create_ticket", args, reason="register_ticket")
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "register_ticket", str(e), level="error")


def simulate_router_reboot_action(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_REBOOT=on): reflect the caller power-cycling the
    router (S6) — the demo port flaps and traffic returns, so the reboot-check
    telemetry read sees what a real reboot produces. Off by default → live demo
    calls use the „Perkrauti routerį" button instead (the human plays the
    physical world); production sees the real flap on its own."""
    from .walker_flow import note_evidence

    if os.getenv("SIMULATE_REBOOT", "off").lower() != "on":
        return
    cid = state.identity.customer_id
    if not cid:
        return
    try:
        res = rt.tools.run(
            state,
            rt,
            "simulate_router_reboot",
            {"customer_id": cid},
            reason="simulate_reboot",
            apply=False,
        ).data
        if res.get("success"):
            note_evidence(state, rt, "klientas perkrovė routerį — portas mirktelėjo (simuliuota)")
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"router reboot sim failed: {e}")
        trace_note(rt.tracer, state, "reboot_sim", str(e))


def simulate_bridge_connection(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
    wall cable by making an unbound device appear on the line, so the bridge can
    VERIFY it. Off by default → production never fakes a device (the real one appears
    on its own). Best-effort: a failure just leaves the line unchanged."""
    from .walker_flow import note_evidence

    if os.getenv("SIMULATE_BRIDGE", "off").lower() != "on":
        return
    cid = state.identity.customer_id
    if not cid:
        return
    try:
        res = rt.tools.run(
            state,
            rt,
            "simulate_bridge_connect",
            {"customer_id": cid},
            reason="simulate_bridge",
            apply=False,
        ).data
        if res.get("success"):
            note_evidence(state, rt, "klientas prijungė įrenginį — matomas linijoje (simuliuota)")
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"bridge connection sim failed: {e}")
        trace_note(rt.tracer, state, "bridge_sim", str(e))
