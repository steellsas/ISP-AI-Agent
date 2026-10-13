"""Ticket execution — the contact ladder before every registration: the dialogue begins
on an escalate step, the ticket is registered from STATE when it finishes, a registered
ticket's note can be amended, and the narrator never claims a registration that did not
happen."""

from __future__ import annotations

import re
from typing import Any

from ..contract.locale import vocab


def _begin_ticket_dialogue(state: Any, rt: Any) -> None:
    """Start the ticket-confirmation dialogue: before ANY registration the agent
    collects the contact number (ALWAYS asked — the caller may be on a
    company/other phone, or the DB number stale) and when it is convenient to
    call. The scripted ladder asks; once complete, finish_ticket_dialogue
    registers with the contacts on the ticket."""
    if state.ticket.ticket_id or state.ticket.stage:
        return  # already registered / already collecting
    from ..graph_v2.state import TicketContext

    state.ticket.context = TicketContext()
    state.ticket.stage = "phone"
    rt.tracer.emit("decision", intent="ticket_dialogue", action="start")


def request_ticket(state: Any, rt: Any, why: str, *, request_type: str | None = None) -> None:
    """THE one way a registration starts (STRUKTURA_V3 stage 3b — eleven places used to start
    the contact dialogue each in its own way).

    `why` is one of the reasons in `knowledge/registracija.yaml` — the engine registers for
    nothing else (an unknown reason raises). It goes to the trace and onto the ticket. A request
    for the responsible person carries its `request_type`; a fault gets its card's note for the
    technician. Nothing happens when a registration is already running or done.
    """
    from ..contract.registration import check

    check(why)
    if state.ticket.ticket_id or state.ticket.stage:
        return
    state.ticket.reason = why
    if request_type:
        state.ticket.request_type = request_type
    elif state.case.fault:
        from ..contract import cards

        card = cards.card(state.case.fault)
        if card is not None and card.escalate and card.escalate.note:
            state.case.facts.setdefault("_ticket_note", card.escalate.note)
    rt.tracer.emit(
        "decision",
        intent="ticket_requested",
        action=why,
        value=request_type or state.case.fault,
    )
    _begin_ticket_dialogue(state, rt)


def fmt_phone(nr: str | None) -> str:
    """Group a dialable number for TTS ("+370 600 12353"); free text passes through."""
    raw = (nr or "").strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if len(re.sub(r"\D", "", digits)) < 6 or digits != raw:
        return raw
    if digits.startswith("+370") and len(digits) == 12:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return digits


def append_ticket_note(state: Any, rt: Any, note: str, kind: str = "correction") -> bool:
    """Post-registration correction (live 2026-08-25: the caller gave a NEW
    call-back number after 'Užregistravau' and it vanished into the goodbye).
    Appends the note to the registered ticket's details so the worker sees it.
    Best-effort: False on any hiccup — the spoken acknowledgement then still
    happens, but the trace records note_failed."""
    tid = state.ticket.ticket_id
    if not tid or not note:
        return False
    try:
        result = rt.tools.run(
            state,
            rt,
            "append_ticket_note",
            {"ticket_id": tid, "note": note, "kind": kind},
            reason="ticket_amend",
            apply=False,
        )
        return bool(result.data.get("success"))
    except Exception:  # a failed note must never break the goodbye
        import logging

        logging.getLogger(__name__).warning("ticket note amend failed", exc_info=True)
        return False


def finish_ticket_dialogue(state: Any, rt: Any) -> str:
    """All contacts collected (or defaulted) — register, close, announce. The
    announce repeats the number and hours back, so "kokiu numeriu?" never needs
    asking (observed live: the caller asked twice and got a goodbye)."""
    from ..contract.locale import phrase
    from ..executor_flow import register_ticket_from_state

    s = state
    if not s.ticket.contact_phone:
        s.ticket.contact_phone = s.identity.caller_phone  # default: the number they call from
    if not s.ticket.contact_hours:
        s.ticket.contact_hours = phrase("ticket.default_hours")
    ctx = state.ticket.context
    note = (ctx.note if ctx else None) or ""
    state.ticket.stage = None
    state.ticket.context = None
    from ..decide.question import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ticket")  # contacts collected — the dialogue is over
    register_ticket_from_state(state, rt)
    from ..closing import close_call

    close_call(state, rt, "registered" if s.ticket.ticket_id else "declined")
    val = s.ticket.contact_hours.rstrip(".")  # the template ends the sentence itself
    val = val[:1].lower() + val[1:]  # mid-sentence: "skambinti galima bet kada"
    done = (
        "identification.ticket_done_request"
        if s.ticket.request_type
        else "identification.ticket_done"
    )
    return phrase(done, phone=fmt_phone(s.ticket.contact_phone), hours=val) + note


def unbacked_promise(state: Any, sentence: str) -> bool:
    """A registration promise the ENGINE has not decided — the sentence is not spoken.

    Andrius (2026-10-13): the engine decides, the speaking model only says what it decided.
    Until then a model's „užregistruosiu" was turned INTO a registration (the claim guard,
    wave 9) — a word became a decision: mid-identification („…kad viską teisingai
    užregistruosiu?") a ticket was opened for nothing (eval S1). Now a promise is spoken only
    when the engine has decided to register: a registration is running or done, or the Case has
    summed up for a technician (the registration starts on its next turn).
    """
    low = (sentence or "").lower()
    if not any(m in low for m in vocab("registration_claim")):
        return False
    if not any(m in low for m in vocab("registration_claim_subject")):
        return False
    from ..decide.rules.head import case_owes_ticket

    s = state
    decided = bool(s.ticket.ticket_id or s.ticket.stage) or case_owes_ticket(s)
    return not decided
