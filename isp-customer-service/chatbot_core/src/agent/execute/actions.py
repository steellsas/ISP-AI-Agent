"""Plan actions — each action name maps to the engine code that performs it.

An action may return words (an engine-composed reply, e.g. the ticket dialogue's first
question); the plan's say decides whether they are spoken.
"""

from __future__ import annotations

from typing import Any


def run_action(state: Any, rt: Any, plan: Any) -> str | None:
    action = plan.action
    if action.type == "none":
        return None
    if action.type == "close":
        close_call(state, rt, action.name or "declined", **action.args)
        return None
    if action.type == "tool" and action.name == "preflight_phone":
        from .identification import preflight_phone

        preflight_phone(state, rt)
        return None
    if action.type == "procedure_step" and action.name == "run_due_action":
        from .diagnosis import ensure_action_done

        ensure_action_done(state, rt)
        return None
    if action.type == "procedure_step" and action.name == "escalate":
        from ..decide.rules.diagnosis import drive_escalate

        return drive_escalate(state, rt, None)
    if action.type == "register_ticket" and action.name == "auto":
        from ..executor_flow import register_ticket_from_state

        register_ticket_from_state(state, rt, None)  # the inform news promises it
        return None
    if action.type == "register_ticket":
        from .ticket import finish_ticket_dialogue

        return finish_ticket_dialogue(state, rt)
    if action.type == "append_ticket":
        from .ticket import append_ticket_note

        noted = append_ticket_note(state, rt, action.args.get("note", ""))
        rt.tracer.emit(
            "decision", intent="ticket_amend", action="phone_noted" if noted else "note_failed"
        )
        return None
    raise ValueError(f"no executor for action {action.type}:{action.name}")


def close_call(state: Any, rt: Any, reason: str, complete: bool = False) -> None:
    """End the case — the ONE place a call closes (wave 1: every rule plans this action
    instead of writing the closing flags itself, so the gate sees it and the trace
    records it). `complete` also hangs up: the words that go out with the plan ARE the
    goodbye. reason="stuck" is the backstop's close, which keeps the registration an
    identified caller was promised (F-5)."""
    s = state
    if reason == "stuck":
        _close_stuck(state, rt)
    else:
        s.closing.case_closed = True
        s.closing.closed_reason = reason
    if complete:
        s.closing.is_complete = True
    rt.tracer.emit(
        "decision",
        intent="close",
        action=s.closing.closed_reason,
        value="complete" if s.closing.is_complete else "open",
    )


def _close_stuck(state: Any, rt: Any) -> None:
    """The stuck ladder's close: an identified caller gets the fault registered (it was
    promised), an unidentified one is recorded as stuck."""
    from ..executor_flow import register_ticket_from_state

    s = state
    s.closing.case_closed = True
    if not s.identity.customer_id:
        s.closing.closed_reason = "declined"
        s.closing.unidentified_reason = "stuck"
        return
    if s.resolution.procedure is not None:
        s.resolution.procedure["escalate_reason"] = "stuck"
    register_ticket_from_state(s, rt, None)
    s.closing.closed_reason = "registered" if s.ticket.ticket_id else "declined"
