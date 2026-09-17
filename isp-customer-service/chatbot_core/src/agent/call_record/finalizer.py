"""The end of a call (D-14): the hang-up safety net and the contact record it leaves.

Every end path — hang-up, disconnect, TTL, shutdown, eval — runs `finalize` once. A call
that ends mid-procedure with a promised-but-missing ticket registers it from state
(nobody would follow up otherwise); then the outcome is derived from the final state
(`outcome.py`), and the record — outcome, review flag, intent, verdict, outage, ticket,
summary, transcript — is written to the conversations table. How the transport ended is
kept apart from the outcome (F-4).
"""

from __future__ import annotations

import logging

from ..contract.locale import phrase
from ..faults import role_of, verdict_flag
from ..graph_v2.state import GraphState
from ..runtime import AgentRuntime
from ..trace import tools_called_this_session, trace_note

logger = logging.getLogger(__name__)


def finalize(state: GraphState, rt: AgentRuntime, transport_end: str | None = None) -> None:
    """Close the call once (idempotent): the hang-up net, the record, session_end.
    `transport_end` says how the call ended (client_closed, ws_disconnect, expired,
    server_shutdown, eval) — it never becomes the outcome."""
    from ..executor_flow import register_ticket_from_state

    if rt.ended.is_set():
        return
    rt.ended.set()
    # Hang-up safety net (2026-08-05): the call ended MID-STRATEGY with no
    # ticket — the problem is not solved and nobody would follow up (observed
    # live: registration promised, caller hung up via the UI button, ticket
    # never created). Register from state with the interruption on the
    # record; contacts default to the caller-ID number. After-hours
    # philosophy: a human takes over through the ticket.
    s = state
    # F3 (live 2026-09-09): a hang-up ON the homework step means the
    # callback was agreed (or at least offered) — closing with a ticket
    # breaks the agreement (TKT registered over "as perskambinsiu").
    if (
        s.identity.customer_id
        and not s.ticket.ticket_id
        and not s.closing.case_closed
        and role_of(
            (s.resolution.procedure or {}).get("verdict"),
            (s.resolution.procedure or {}).get("step"),
        )
        == "homework"
    ):
        s.closing.case_closed = True
        s.closing.closed_reason = "callback"
        rt.tracer.emit("decision", intent="hangup_net", action="callback_close")
    if (
        s.identity.customer_id
        and not s.ticket.ticket_id
        and not s.closing.case_closed
        and s.resolution.procedure is not None
    ):
        from ..resolution import get_strategy

        # The line's CURRENT truth decides (2026-08-06): a caller who hung up
        # right after "veikia!" must NOT get a technician ticket (observed
        # live: TKT00D19E54 for a healthy line). A recorded fix or one fresh
        # diagnose read showing healthy skips the net; telemetry unreachable
        # -> register anyway (a spare ticket beats an abandoned caller).
        solved = bool(s.resolution.procedure.get("telemetry_fixed"))
        if not solved:
            try:
                from ..tooling import telemetry

                d = telemetry(state, rt, mode="recheck", reason="hangup_net").data
                reason = (d.get("verdict") or {}).get("reason")
                solved = reason is None or verdict_flag(reason, "healthy_up_to_router")
            except Exception:  # pragma: no cover - defensive
                solved = False
        if solved:
            s.closing.case_closed = True
            s.closing.closed_reason = "resolved"
            rt.tracer.emit("decision", intent="hangup_net", action="skip_solved")
        else:
            s.resolution.procedure.setdefault("escalate_reason", "caller_hung_up")
            if not s.ticket.contact_phone:
                s.ticket.contact_phone = s.identity.caller_phone
            if not s.ticket.contact_hours:
                s.ticket.contact_hours = phrase("ticket.default_hours")
            strat = get_strategy(s.resolution.procedure.get("verdict"))
            esc = strat.by_role("escalate") if strat else None
            register_ticket_from_state(state, rt, esc.id if esc is not None else None)
            if s.ticket.ticket_id:
                s.closing.closed_reason = "registered"
                rt.tracer.emit("decision", intent="hangup_net", action="register")
    from .outcome import derive, outage_id

    record = derive(state, technical_error=_technical_error(rt.tracer))
    # Structured summary of the call, built DETERMINISTICALLY from state (Phase 3.10):
    # why they called, the cause + side, what ran, resolved?/ticket, who called.
    summary = build_call_summary(state, rt)
    summary.update(record.as_dict())
    rt.tracer.emit("call_summary", **summary)
    rt.tracer.emit(
        "session_end",
        outcome=record.outcome,
        transport_end=transport_end,
        needs_review=record.needs_review,
        customer_id=state.identity.customer_id,
        ticket_id=state.ticket.ticket_id,
        turn_count=state.dialog.turn_count,
        llm_calls=rt.llm_stats.total_calls,
        total_tokens=rt.llm_stats.total_tokens,
        total_cost=round(rt.llm_stats.total_cost, 5),
    )
    # Best-effort at the seam: a DB failure must never break call teardown.
    _persist_call_record(state, rt, summary, record, transport_end, outage_id(state))
    # Write a human-readable transcript next to the JSONL, if supported.
    export = getattr(rt.tracer, "export_txt", None)
    if callable(export):
        export()


def _technical_error(tracer) -> bool:
    """A turn failed on a technical error (the voice turn fell over, an error-level note)."""
    import json
    from pathlib import Path

    path = getattr(tracer, "path", None)
    if not path:
        return False
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if '"error"' not in line:
                continue
            e = json.loads(line)
            if e.get("type") == "error" and e.get("level", "error") == "error":
                return True
    except Exception:  # pragma: no cover - best-effort
        return False
    return False


def _persist_call_record(
    state: GraphState,
    rt: AgentRuntime,
    summary: dict,
    record,
    transport_end: str | None,
    outage: str | None,
) -> None:
    """Write the call's one row to the conversations table, keyed by session. Sourced
    entirely from state; never raises."""
    session_id = getattr(rt.tracer, "session_id", None)
    if not session_id:
        return  # NullTracer / no session id -> nothing to key the record on
    try:
        from datetime import timedelta

        from ..contract import limits
        from ..tools import save_call_record

        s = state
        retention = None
        if not s.identity.customer_id:
            # Privacy (D-14): the audio of an unidentified caller is kept only so long.
            days = limits.get("audio_retention_days_unidentified")
            retention = (rt.clock() + timedelta(days=days)).date().isoformat()
        save_call_record(
            session_id,
            customer_id=s.identity.customer_id,
            messages=s.messages,
            outcome=record.outcome,
            summary=summary,
            ticket_id=s.ticket.ticket_id or s.closing.appended_ticket_id,
            duration_seconds=int((rt.clock() - rt.started_at).total_seconds()),
            transport_end=transport_end,
            unidentified_reason=record.unidentified_reason,
            needs_review=record.needs_review,
            review_reason=record.review_reason,
            intent=s.intake.problem_type,
            verdict=(s.diagnosis.verdicts.get("network") or {}).get("reason"),
            address_confirmed=bool(s.identity.address_confirmed),
            outage_id=outage,
            audio_retention_until=retention,
        )
    except Exception as e:  # pragma: no cover - defensive
        trace_note(rt.tracer, state, "persist_call_record", f"failed: {e}", level="warn")


def build_call_summary(state: GraphState, rt: AgentRuntime) -> dict:
    """The call's outcome, derived from state — the single source for the record and
    (later) the ticket. No LLM, no new reasoning: it only reports what the engine knows.
    `actions` come from the tool_calls in this session's trace."""
    s = state
    net = s.diagnosis.verdicts.get("network") or {}
    h = s.diagnosis.hypothesis or {}
    cause = h.get("cause") or (s.resolution.procedure or {}).get("verdict") or net.get("reason")
    return {
        "purpose": s.intake.problem_type,
        "customer_id": s.identity.customer_id,
        "address": s.identity.customer_address,
        "caller_name": s.identity.caller_name,
        "caller_relation": s.identity.caller_relation,
        "anamnesis": (
            {
                "raw": s.intake.anamnesis_raw,
                "when": s.intake.anamnesis_when,
                "trigger": s.intake.anamnesis_trigger,
            }
            if s.intake.anamnesis_raw
            else None
        ),
        "cause": cause,
        "side": net.get("side"),  # provider | customer | unclear
        "closed_reason": s.closing.closed_reason,  # resolved | outage | declined | registered | None
        "resolved": s.closing.closed_reason == "resolved",
        "ticket_id": s.ticket.ticket_id,
        "actions": tools_called_this_session(rt.tracer),
        # F4 (Andrius 2026-08-20): a call that ended WITHOUT identification
        # records everything that was heard — the address may have changed
        # its name, the caller may not be the holder; a person reading the
        # record (or the caller phoning back) can pick the thread up.
        "identifikacija_nepavyko": (
            {
                "girdeta": list(s.intake.heard_utterances)[-6:],
                "gatve": s.identity.profile.street.value,
                "namas": s.identity.profile.house.value,
                "miestas": s.identity.profile.city.value,
            }
            if not s.identity.customer_id and s.intake.problem_type
            else None
        ),
    }
