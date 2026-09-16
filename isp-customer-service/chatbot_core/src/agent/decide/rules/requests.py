"""Request rules (D-11, owner 2026-09-16) — what the agent registers or answers, not solves.

A `register` intent (a bill, a contract, moving, a wish) is outside the agent's knowledge:
it is never answered or explained. After identification the caller's own words become a
ticket of the intent's type for the responsible person, through the same contact dialogue
a fault ticket uses. An `answer` intent (the status of a registration) is answered from
the customer's open tickets.
"""

from __future__ import annotations

from typing import Any


def start_request(state: Any, rt: Any) -> None:
    """Register the caller's question for the responsible person (contacts first)."""
    from ...execute.ticket import begin_ticket_dialogue
    from ...intents import problem_entry

    ticket_type = problem_entry(state.intake.problem_type).get("ticket_type")
    state.ticket.request_type = ticket_type
    rt.tracer.emit("decision", intent="request", action="register", value=ticket_type)
    begin_ticket_dialogue(state, rt, None)


def answer_ticket_status(state: Any, rt: Any) -> None:
    """The status of the caller's registration — or that there is none open."""
    from . import open_ticket

    if state.identity.open_tickets:
        open_ticket.repeat_call(state, rt, state.identity.open_tickets[0])
        return
    state.diagnosis.verdicts["network"] = {"reason": "no_open_ticket", "skipped": True}
    rt.tracer.emit("verdict", reason="no_open_ticket", source="open_tickets")
