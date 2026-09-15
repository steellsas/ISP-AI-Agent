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
    if action.type == "tool" and action.name == "preflight_phone":
        from ..identification_flow import preflight_phone

        preflight_phone(state, rt)
        return None
    if action.type == "procedure_step" and action.name == "escalate":
        from ..solver_flow import drive_escalate

        return drive_escalate(state, rt, None)
    if action.type == "register_ticket":
        from ..ticket_flow import finish_ticket_dialogue

        return finish_ticket_dialogue(state, rt)
    if action.type == "append_ticket":
        from ..ticket_flow import amend_ticket_note

        noted = amend_ticket_note(state, rt, action.args.get("note", ""))
        rt.tracer.emit(
            "decision", intent="ticket_amend", action="phone_noted" if noted else "note_failed"
        )
        return None
    raise ValueError(f"no executor for action {action.type}:{action.name}")
