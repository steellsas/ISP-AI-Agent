"""
Executor flow — the ONLY place tools run and tickets are registered.

The STATE-driven idempotent ticket registration and the demo bridge simulation
(the engine runs every tool through the gateway; the LLM calls none). Functions take
(state, rt) — the call state and the AgentRuntime. tools run through rt.tools (the
gateway).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .contract.locale import phrase_or
from .trace import tools_called_this_session, trace_note

logger = logging.getLogger(__name__)


def register_ticket_from_state(state: Any, rt: Any, step_id: str | None) -> None:
    """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
    cause from the hypothesis/verdict, actions from this call's trace — never from
    the model's free text (which once invented an invalid ticket_type). Idempotent:
    an existing ticket is never duplicated. Best-effort: a failure is traced and the
    close still proceeds (the call record keeps the outcome)."""

    s = state
    if s.ticket.ticket_id or not s.identity.customer_id:
        return
    if s.ticket.request_type:
        _register_request(state, rt)
        return
    cause = (
        (s.diagnosis.hypothesis or {}).get("cause")
        or (s.resolution.procedure or {}).get("verdict")
        or ""
    )
    from .contract.locale import phrase

    gloss = phrase_or(f"verdict.{cause}.gloss", cause or phrase("ticket.details.unknown_cause"))
    details = phrase(
        "ticket.details.fault",
        problem=s.intake.problem_type or phrase("ticket.details.default_problem"),
        gloss=gloss,
    )
    need = phrase_or(f"verdict.{cause}.ticket_need", None)
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
        kas = s.identity.caller_name or phrase("ticket.details.default_contact")
        rel = f" ({s.identity.caller_relation})" if s.identity.caller_relation else ""
        details += phrase(
            "ticket.details.contact",
            who=kas,
            relation=rel,
            phone=s.ticket.contact_phone or s.identity.caller_phone,
        )
        if s.ticket.contact_hours:
            details += phrase("ticket.details.contact_hours", hours=s.ticket.contact_hours)
        details += "."
    # The caller's anamnesis rides on the ticket — the human sees WHEN it broke
    # and after what, not just the telemetry verdict (Step 2 analysis).
    if s.intake.anamnesis_when or s.intake.anamnesis_trigger or s.intake.anamnesis_raw:
        bits = []
        if s.intake.anamnesis_when:
            bits.append(
                phrase(
                    "ticket.details.anamnesis_when",
                    when=phrase_or(
                        f"anamnesis.when.{s.intake.anamnesis_when}", s.intake.anamnesis_when
                    ),
                )
            )
        if s.intake.anamnesis_trigger:
            bits.append(
                phrase(
                    "ticket.details.anamnesis_trigger",
                    trigger=phrase_or(
                        f"anamnesis.trigger.{s.intake.anamnesis_trigger}",
                        s.intake.anamnesis_trigger,
                    ),
                )
            )
        details += phrase(
            "ticket.details.anamnesis", text=", ".join(bits) if bits else s.intake.anamnesis_raw
        )
    from .faults import role_of

    if role_of((s.resolution.procedure or {}).get("verdict"), step_id) == "register_after_bridge":
        details += phrase("ticket.details.bridge_router")
    # Ledger: what the CALLER established (client-side evidence) — the human
    # taking over sees the checked physical facts, not just telemetry.
    client_bits = []
    from .evidence import CLIENT as _EV_CLIENT
    from .evidence import gloss_label, gloss_value

    for key, e in s.diagnosis.evidence.items():
        if e.get("source") == _EV_CLIENT and not e.get("conflict"):
            client_bits.append(f"{gloss_label(key)}: {gloss_value(e['value'], key)}")
    if client_bits:
        details += phrase("ticket.details.checked", facts="; ".join(client_bits))
    # Why it was not solved (refusal / demand / not home) — recorded on the ticket
    # so the technician knows the context (policy 2026-07-30).
    reason = (s.resolution.procedure or {}).get("escalate_reason")
    if reason:
        details += f" {phrase(f'ticket.reason.{reason}')}"
    # What was already TRIED and ruled out — the human taking over must not redo
    # it (after-hours philosophy 2026-08-03: the agent attempts, a person takes
    # over via the ticket with the full attempt history).
    tried = list(s.diagnosis.failed_hypotheses) + [
        x.get("cause") for x in s.diagnosis.rejected_hypotheses if x.get("cause")
    ]
    if tried:
        glosses = ", ".join(phrase_or(f"verdict.{c}.gloss", c) for c in dict.fromkeys(tried))
        details += phrase("ticket.details.tried", causes=glosses)
    # A (2026-08-21): secondary problems the caller mentioned mid-call — the
    # technician checks them on the same visit.
    if getattr(s.intake, "secondary_problems", None):
        extra = "; ".join(
            phrase("ticket.details.extra_item", type=x["type"], text=x["text"])
            for x in s.intake.secondary_problems
        )
        details += phrase("ticket.details.extra", items=extra)
    from .ticket_types import fault_type

    actions = tools_called_this_session(rt.tracer)
    args = {
        "customer_id": s.identity.customer_id,
        "ticket_type": fault_type((s.resolution.procedure or {}).get("verdict")),
        "problem_type": s.intake.problem_type,
        "problem_description": details,
        "notes": phrase("ticket.details.actions", tools=", ".join(actions)) if actions else "",
    }
    try:
        # The state update sets ticket_id.
        rt.tools.run(state, rt, "create_ticket", args, reason="register_ticket")
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "register_ticket", str(e), level="error")


def _register_request(state: Any, rt: Any) -> None:
    """A question for the responsible person: the caller's own words, typed by intent, with
    who to call and when — nothing interpreted (the agent does not know this area)."""
    from .contract.locale import phrase
    from .intents import intent_for_ticket_type
    from .perceive.nlu import classify_problem

    s = state
    # What the caller said about it — not the "Taip" / name answers of identification.
    heard = s.intake.heard_utterances
    about = [u for u in heard if classify_problem(u) == s.intake.problem_type] or heard[:1]
    said = s.ticket.request_note or " / ".join(about[:3]) or s.intake.problem_type or ""
    details = phrase(
        "ticket.details.request",
        type=phrase_or(f"request_label.{s.ticket.request_type}", s.ticket.request_type),
        text=said,
    )
    if s.ticket.contact_phone or s.identity.caller_name:
        details += phrase(
            "ticket.details.contact",
            who=s.identity.caller_name or phrase("ticket.details.default_contact"),
            relation=f" ({s.identity.caller_relation})" if s.identity.caller_relation else "",
            phone=s.ticket.contact_phone or s.identity.caller_phone,
        )
        if s.ticket.contact_hours:
            details += phrase("ticket.details.contact_hours", hours=s.ticket.contact_hours)
        details += "."
    args = {
        "customer_id": s.identity.customer_id,
        "ticket_type": s.ticket.request_type,
        # What the request is about (a disputed debt on an internet call is `billing`):
        # a later call about the internet is not a repeat of it (D-12).
        "problem_type": intent_for_ticket_type(s.ticket.request_type) or s.intake.problem_type,
        "problem_description": details,
    }
    try:
        rt.tools.run(state, rt, "create_ticket", args, reason="register_request")
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "register_request", str(e), level="error")


def simulate_router_reboot_action(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_REBOOT=on): reflect the caller power-cycling the
    router (S6) — the demo port flaps and traffic returns, so the reboot-check
    telemetry read sees what a real reboot produces. Off by default → live demo
    calls use the „Perkrauti routerį" button instead (the human plays the
    physical world); production sees the real flap on its own."""

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
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"router reboot sim failed: {e}")
        trace_note(rt.tracer, state, "reboot_sim", str(e))


def simulate_bridge_connection(state: Any, rt: Any) -> None:
    """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
    wall cable by making an unbound device appear on the line, so the bridge can
    VERIFY it. Off by default → production never fakes a device (the real one appears
    on its own). Best-effort: a failure just leaves the line unchanged."""

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
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning(f"bridge connection sim failed: {e}")
        trace_note(rt.tracer, state, "bridge_sim", str(e))
