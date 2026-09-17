"""Request rules (D-11, owner 2026-09-16) — what the agent registers or answers, not solves.

A `register` intent (a bill, a contract, moving, a wish) is outside the agent's knowledge:
it is never answered or explained. After identification the caller's own words become a
ticket of the intent's type for the responsible person, through the same contact dialogue
a fault ticket uses. An `answer` intent (the status of a registration) is answered from
the customer's open tickets.
"""

from __future__ import annotations

from typing import Any


def start_request(state: Any, rt: Any, ticket_type: str | None = None) -> None:
    """Register the caller's question for the responsible person (contacts first)."""
    from ...execute.ticket import begin_ticket_dialogue
    from ...intents import problem_entry

    ticket_type = ticket_type or problem_entry(state.intake.problem_type).get("ticket_type")
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


def disputes_debt(text: str | None) -> bool:
    """The caller disagrees with the debt or does not understand it."""
    from ...contract.locale import vocab

    low = (text or "").lower()
    return any(m in low for m in vocab("debt_dispute"))


def debt_dispute_due(state: Any, user_input: str | None) -> bool:
    """The caller was told about a debt and now disputes it — the offer is due."""
    from ...faults import verdict_flag

    reason = (state.diagnosis.verdicts.get("network") or {}).get("reason")
    return bool(
        state.closing.debt_offer is None
        and not state.ticket.request_type
        and state.diagnosis.news_delivered
        and verdict_flag(reason, "inform") == "debt"
        and disputes_debt(user_input)
    )


def debt_offer_turn(state: Any, rt: Any, user_input: str | None) -> str | None:
    """After the debt news: a dispute gets the offer to register it for the responsible
    person — the agent does not explain bills. Returns "ask" (the offer goes out now),
    "start" (they agreed: the contact dialogue starts), or None (not this rule's turn)."""
    from ..question import clear, register

    c = state.closing
    if c.debt_offer == "asked":
        c.debt_offer = "answered"
        clear(state, rt, "debt_offer")
        from ...perceive.detectors import detect_ticket_consent

        if detect_ticket_consent(user_input) == "yes":
            start_request(state, rt, "billing_request")
            return "start"
        rt.tracer.emit("decision", intent="debt_offer", action="declined")
        return None
    if debt_dispute_due(state, user_input):
        c.debt_offer = "asked"
        state.ticket.request_note = (user_input or "").strip()[:200]
        register(state, rt, "inform", "debt_offer")
        rt.tracer.emit("decision", intent="debt_offer", action="ask")
        return "ask"
    return None
