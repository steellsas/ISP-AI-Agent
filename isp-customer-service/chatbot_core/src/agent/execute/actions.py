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
        from ..closing import close_call

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
