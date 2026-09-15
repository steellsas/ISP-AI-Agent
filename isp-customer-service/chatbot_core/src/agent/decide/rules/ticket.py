"""Ticket rules — the contact dialogue before a registration (§5 row 3).

The caller's answer to the number / hours question is read first (capture, one retry
each, the cancel-confirm, the callback wish); then the dialogue asks its next
question, registers once both contacts are known, or ends on a confirmed refusal.
"""

from __future__ import annotations

from typing import Any

from ..plan import Action, Say, TurnPlan

STAGE = "ticket"


def plan(state: Any, rt: Any) -> TurnPlan | None:
    from ...perception_flow import ticket_capture
    from ...ticket_flow import ticket_question_turn

    s = state
    user_input = s.turn.user_input
    if s.ticket.stage not in ("phone", "hours") or not user_input or s.closing.case_closed:
        return None
    ticket_capture(state, rt, user_input)
    # A first-person "I will call back" closed the dialogue — the warm goodbye.
    if s.closing.callback_goodbye_due:
        s.closing.callback_goodbye_due = False
        return _scripted("ticket.callback_close", key="identification.callback_goodbye")
    if s.ticket.stage in ("phone", "hours"):
        rule, words = ticket_question_turn(state, rt)
        if words is None:
            return TurnPlan(owner="ticket", rule=rule, say=Say(kind="directive", stage=STAGE))
        return _scripted(rule, text=words)
    if s.ticket.stage == "done":
        return TurnPlan(
            owner="ticket",
            rule="ticket.register",
            action=Action(type="register_ticket"),
            say=Say(kind="phrase", stage=STAGE),
        )
    if s.ticket.stage == "cancelled":
        from ...contract.locale import phrase

        s.ticket.stage = None
        s.ticket.context = None
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        s.closing.is_complete = True
        return _scripted(
            "ticket.cancelled", text=phrase("ticket.declined") + phrase("identification.goodbye")
        )
    # The caller refused the registration but wants to keep solving — the narrator
    # says so and re-anchors the last instruction.
    return TurnPlan(
        owner="ticket", rule="ticket.back_to_solving", say=Say(kind="directive", stage=STAGE)
    )


def _scripted(rule: str, key: str | None = None, text: str | None = None) -> TurnPlan:
    return TurnPlan(
        owner="ticket", rule=rule, say=Say(kind="phrase", key=key, text=text, stage=STAGE)
    )
