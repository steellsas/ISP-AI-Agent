"""Open-ticket rules (D-12) — a repeat call is a note on the ticket, never a duplicate.

When the identified customer's problem already has an open ticket, the call is not
diagnosed again and no new ticket is made: what the caller says goes onto that ticket as
a repeat-call note (just checking, or nobody came), and they hear its status. A different
problem takes the normal path.
"""

from __future__ import annotations

from typing import Any


def told_ticket(state: Any) -> dict[str, Any] | None:
    """The ticket the caller is being told about: the one the call's note went on."""
    tid = state.closing.appended_ticket_id
    for ticket in state.identity.open_tickets or []:
        if ticket.get("ticket_id") == tid:
            return ticket
    return same_problem_ticket(state)


def same_problem_ticket(state: Any) -> dict[str, Any] | None:
    """The open ticket for the problem this caller reports, or None."""
    problem = state.intake.problem_type
    if not problem:
        return None
    for ticket in state.identity.open_tickets or []:
        if ticket.get("problem_type") == problem:
            return ticket
    return None


def note_kind(state: Any) -> str:
    """What the repeat call is: nobody came, or the caller is checking on it."""
    from ...contract.locale import vocab

    heard = " ".join(state.intake.heard_utterances[-3:]).lower()
    if any(m in heard for m in vocab("repeat_nobody_came")):
        return "nobody_came"
    return "just_checking"


def repeat_call(state: Any, rt: Any, ticket: dict[str, Any] | None = None) -> None:
    """Note the repeat call on the open ticket and answer with its status."""
    ticket = ticket or same_problem_ticket(state) or {}
    tid = ticket.get("ticket_id")
    kind = note_kind(state)
    said = " / ".join(state.intake.heard_utterances[-3:]) or state.intake.problem_type or ""
    try:
        rt.tools.run(
            state,
            rt,
            "append_ticket_note",
            {"ticket_id": tid, "note": said, "kind": kind},
            reason="repeat_call",
            apply=False,
        )
    except Exception as e:  # pragma: no cover - a failed note must not break the answer
        from ...trace import trace_note

        trace_note(rt.tracer, state, "repeat_call", str(e), level="error")
    state.closing.appended_ticket_id = tid
    state.diagnosis.verdicts["network"] = {"reason": "open_ticket_exists", "skipped": True}
    rt.tracer.emit("verdict", reason="open_ticket_exists", source="open_tickets")
    rt.tracer.emit("decision", intent="repeat_call", action="append", key=tid, value=kind)
