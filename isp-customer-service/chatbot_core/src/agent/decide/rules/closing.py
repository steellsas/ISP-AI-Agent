"""Closing rules — the turns after the case is closed (§5 row 2).

A ticket demand or a "still not working" at the goodbye reopens the case and starts
the registration; a number correction after the registration lands on the ticket;
otherwise the call ends on one short goodbye — only the first closing reply (or a real
question) is the LLM's.
"""

from __future__ import annotations

import re
from typing import Any

from ...closing import close_call, hang_up, reopen_call
from ...contract import limits
from ...faults import verdict_flag
from ..plan import Action, Say, TurnPlan

STAGE = "closing"


def plan(state: Any, rt: Any) -> TurnPlan | None:
    from ...perceive.detectors import detect_refuse_or_ticket

    s = state
    if not s.closing.case_closed:
        return None
    user_input = s.turn.user_input
    # A ticket demand at the goodbye reopens the case (live 2026-08-13: "Dar prašau,
    # žegistruokit gedimą…" got "gražios dienos!" and the caller left with
    # ticket=None) — the registration dialogue starts instead of the farewell.
    if (
        user_input
        and detect_refuse_or_ticket(user_input) == "demand"
        and not s.ticket.ticket_id
        and _was_a_fault(s)
    ):
        reopen_call(state, rt, "ticket_demand")
        return _escalate(state, rt, "closing.ticket_demand_reopen")
    # A "still not working" at the goodbye contradicts a resolved close — never wave
    # it off (live 2026-09-11: "Internetas neveikia." got "Geros dienos!").
    if (
        user_input
        and s.closing.closed_reason == "resolved"
        and not s.ticket.ticket_id
        and _was_a_fault(s)
        and _still_down(user_input, _asked_anything_else(s))
    ):
        reopen_call(state, rt, "still_down")
        return _escalate(state, rt, "closing.still_down_reopen")
    # A POST-registration contact correction ("skambinkite kitu numeriu 868…") must land on
    # the ticket, not vanish into the goodbye — read back first, before the goodbye logic can
    # hang up on it.
    amend = _post_registration_phone(state, rt, user_input)
    if amend is not None:
        return amend
    maybe_finish(state, rt, user_input)
    from ...perceive.detectors import is_real_question

    question = is_real_question(user_input)
    # After a REGISTRATION the goodbye is scripted (live 2026-08-21: the closing LLM
    # re-asked the call-back hours after the ticket was done).
    if s.ticket.ticket_id and not question:
        if s.intake.secondary_problems and not s.closing.secondary_problems_asked:
            s.closing.secondary_problems_asked = True  # the facts directive carries the list
        else:
            return _goodbye("closing.goodbye_after_ticket")
    # Closing wave block 4 (live 2026-09-08): the FIRST closing reply may be the
    # LLM's warm close — every trailing non-question turn gets the short goodbye.
    if not question and (
        s.closing.is_complete or s.closing.closing_turns >= limits.get("closing_llm_replies_max")
    ):
        return _goodbye("closing.goodbye")
    return TurnPlan(
        owner="closing", rule="closing.free_reply", say=Say(kind="directive", stage=STAGE)
    )


def _post_registration_phone(state: Any, rt: Any, user_input: str | None) -> TurnPlan | None:
    """A number said after the registration goes on the ticket only once it is read back
    („Užrašiau … — ar teisingai?") and confirmed — the contact dialogue's read-back, kept in
    a `TicketContext` while `ticket.stage` stays None. None = not this rule's turn."""
    from ...perceive.detectors import is_real_question

    s = state
    if not s.ticket.ticket_id or s.closing.is_complete:
        return None
    ctx = s.ticket.context
    if ctx is not None and ctx.phone_confirm_out and ctx.phone_pending:
        ctx.phone_confirm_out = False
        return _read_back_answer(state, rt, ctx, user_input or "")
    reask = ctx is not None and ctx.last_kind == "phone_reask"
    number = _said_number(user_input)
    if number and (reask or not is_real_question(user_input)):
        return _offer_number(state, rt, number)
    if reask:
        s.ticket.context = None  # no number after „pasakykite dar kartą" — the ticket stays
        rt.tracer.emit("decision", intent="ticket_amend", action="phone_dropped")
    return None


def _said_number(user_input: str | None) -> str | None:
    said = re.sub(r"[^\d+]", "", user_input or "")
    return said[:20] if len(re.sub(r"\D", "", said)) >= 6 else None


def _offer_number(state: Any, rt: Any, number: str) -> TurnPlan:
    """A said number: the one already on the ticket (or the caller ID) changes nothing; any
    other is read back and waits for the answer."""
    from ...execute.ticket import caller_id
    from ...graph_v2.state import TicketContext
    from .ticket import _same_phone

    s = state
    known = [p for p in (s.ticket.contact_phone, caller_id(state)) if p]
    if any(_same_phone(number, p) for p in known):
        s.ticket.context = None
        rt.tracer.emit("decision", intent="ticket_amend", action="phone_already_on_ticket")
        return _phone_fixed("closing.ticket_phone_kept", s.ticket.contact_phone or known[0])
    s.ticket.context = TicketContext(phone_pending=number)
    rt.tracer.emit("decision", intent="ticket_amend", action="phone_confirm")
    return _read_back(s.ticket.context)


def _read_back_answer(state: Any, rt: Any, ctx: Any, user_input: str) -> TurnPlan | None:
    """The answer to the read-back, read as in the contact dialogue: a yes or the same number
    writes it on the ticket, a new number is read back, a no asks for it again, a question is
    answered and the read-back stays, a goodbye ends the call with the number left
    unconfirmed (the finalizer notes it), an unclear answer repeats the read-back once."""
    from ...contract.locale import phrase
    from .ticket import phone_confirm_answer

    s = state
    kind, number = phone_confirm_answer(state, rt, ctx.phone_pending, user_input)
    if kind in ("same", "yes"):
        confirmed = ctx.phone_pending
        s.ticket.contact_phone = confirmed
        s.ticket.context = None
        plan = _phone_fixed("closing.ticket_phone_amend", confirmed)
        plan.action = Action(
            type="append_ticket",
            args={"note": phrase("ticket.details.phone_amend", phone=confirmed)},
        )
        return plan
    if kind == "new":
        return _offer_number(state, rt, number)
    if kind == "question":
        ctx.phone_confirm_out = True  # the next answer is still read against the read-back
        return TurnPlan(
            owner="closing", rule="closing.free_reply", say=Say(kind="directive", stage=STAGE)
        )
    if kind == "farewell":
        rt.tracer.emit("decision", intent="ticket_amend", action="phone_unconfirmed")
        return _goodbye("closing.goodbye_after_ticket")
    if kind == "cancel":
        s.ticket.context = None
        rt.tracer.emit("decision", intent="ticket_amend", action="phone_dropped")
        return None
    if kind != "no" and not ctx.phone_confirm_unclear:
        ctx.phone_confirm_unclear = True
        rt.tracer.emit("decision", intent="ticket_amend", action="phone_confirm_repeat")
        return _read_back(ctx)
    ctx.phone_pending = None
    ctx.phone_confirm_unclear = False
    ctx.last_kind = "phone_reask"
    rt.tracer.emit("decision", intent="ticket_amend", action="phone_reask")
    return TurnPlan(
        owner="closing",
        rule="closing.ticket_phone_reask",
        say=Say(kind="phrase", key="identification.ticket_phone_reask", stage=STAGE),
    )


def _read_back(ctx: Any) -> TurnPlan:
    """„Užrašiau {phone} — ar teisingai?" — the next answer is read against it."""
    ctx.phone_confirm_out = True
    return _phone_say("closing.ticket_phone_confirm", "ticket_phone_confirm", ctx.phone_pending)


def _phone_fixed(rule: str, phone: str) -> TurnPlan:
    return _phone_say(rule, "ticket_phone_fixed", phone)


def _phone_say(rule: str, key: str, phone: str) -> TurnPlan:
    from ...execute.ticket import fmt_phone

    return TurnPlan(
        owner="closing",
        rule=rule,
        say=Say(
            kind="phrase",
            key=f"identification.{key}",
            vars={"phone": fmt_phone(phone)},
            stage=STAGE,
        ),
    )


def note_unconfirmed_phone(state: Any, rt: Any) -> None:
    """The call ended while a post-registration number waited for its read-back answer (a
    goodbye, a hang-up): the ticket gets it as an unconfirmed note, its contact stays."""
    from ...contract.locale import phrase
    from ...execute.ticket import append_ticket_note

    ctx = state.ticket.context
    if not state.ticket.ticket_id or ctx is None or not ctx.phone_pending:
        return
    pending, ctx.phone_pending = ctx.phone_pending, None
    noted = append_ticket_note(
        state, rt, phrase("ticket.details.phone_amend_unconfirmed", phone=pending)
    )
    rt.tracer.emit(
        "decision",
        intent="ticket_amend",
        action="phone_noted_unconfirmed" if noted else "note_failed",
    )


def _was_a_fault(s: Any) -> bool:
    """The call worked on a fault (the v2 Case), not news — a technician fits."""
    return bool(s.case.fault)


def _escalate(state: Any, rt: Any, rule: str) -> TurnPlan:
    """Reopen into the contact dialogue and ask its first question in this reply.

    It used to plan `Action(procedure_step, escalate)`, which nothing executes (execute
    raised „no executor"), and both reopen rules were gated on v1's `resolution.procedure`,
    so on a Case call „vis tiek neveikia" at the goodbye got „Geros dienos!" (wave 10, S3/S4).
    """
    from ...execute.ticket import request_ticket
    from .ticket import ticket_question_turn

    request_ticket(state, rt, "vel_neveikia")
    _rule, words = ticket_question_turn(state, rt)
    say = (
        Say(kind="phrase", text=words, stage="ticket")
        if words
        else Say(kind="directive", stage="ticket")
    )
    return TurnPlan(owner="closing", rule=rule, say=say)


def _goodbye(rule: str) -> TurnPlan:
    """The farewell ENDS the call: the words and the hang-up are one plan (wave 1 —
    before, a goodbye-sounding reply was detected afterwards by the narrator)."""
    return TurnPlan(
        owner="closing",
        rule=rule,
        action=Action(type="close", name="keep", args={"complete": True}),
        say=Say(kind="phrase", key="identification.goodbye", stage=STAGE),
    )


def maybe_finish(state: Any, rt: Any, user_input: str | None) -> None:
    """In the closing stage, decide whether to end the call. The case is already
    closed; the agent offered "ar dar kuo nors padėti?". If the caller says a
    goodbye / "no", or we have lingered a second closing turn, set is_complete so
    the transport hangs up — no endless goodbyes."""
    s = state
    if not s.closing.case_closed or s.closing.is_complete:
        return
    s.closing.closing_turns += 1
    from ...perceive.detectors import detect_farewell

    if detect_farewell(user_input) or s.closing.closing_turns >= limits.get("closing_max_turns"):
        hang_up(state, rt)


def maybe_close_inform(state: Any, rt: Any, user_input: str | None) -> None:
    """Deterministic close for INFORM mode (mass outage, billing, or any verdict with
    NO troubleshooting strategy to walk). Once the caller has been informed and
    signals they are done — a goodbye or a plain 'no more questions' — the engine
    closes the call ITSELF and ends it on one farewell.

    Without this, closing depended on the model calling close_case, which it did not:
    the caller said goodbye repeatedly, the call stayed open, and the diagnosis node
    re-narrated the outage every turn (observed: 'repeats the fault')."""
    s = state
    if s.closing.case_closed or not s.identity.customer_id:
        return
    # Farewell may close the INFORM call only after the BUSINESS is done: the
    # identification ladder finished AND the news actually delivered. A garbled
    # mid-ladder "Ne, mano vardas Tomas…" matched the loose farewell heuristic and
    # HUNG UP on the caller before they ever heard the debt (observed live).
    # An OUTAGE report counts as the news told — it is delivered the moment
    # outage_reported flips (a different path than the billing script).
    if (
        state.identity.result_pending
        or state.ticket.stage
        or not (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
        # A fault the Case is still fixing — or has summed up for a technician — is not
        # news. v1 marked it with `resolution.procedure`, which the v2 Case left empty:
        # live 2026-10-07 a dead router was summed up, the caller said „Sutariam, viskas
        # ačiū", and this close beat the registration the Case started in the same turn.
        or s.case.in_progress
        or s.case.summarised
    ):
        return
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    # INFORM mode: an outage was flagged, OR we identified + diagnosed but there is no
    # resolution strategy to walk (active_outage, billing_suspended, generic inform).
    # A live strategy (foreign_mac, dead-router, client-side) keeps s.resolution set
    # and is handled by the walker instead — never closed here.
    inform_mode = s.diagnosis.outage_reported or bool(s.diagnosis.verdicts)
    if not inform_mode:
        return
    from ...perceive.detectors import detect_farewell

    if detect_farewell(user_input):
        why = (
            "outage"
            if (s.diagnosis.outage_reported or verdict_flag(reason, "inform") == "outage")
            else "inform"
        )
        close_call(state, rt, why, complete=True)  # they said goodbye — end on ONE farewell
        # Observability: the close moment was invisible in the trace (this made a
        # stuck-close analysis needlessly hard) — record it.
        rt.tracer.emit(
            "decision", intent="inform_close", action="close", to=s.closing.closed_reason
        )


def _asked_anything_else(state: Any) -> bool:
    """Was our last question „anything else?"."""
    from ...contract.locale import vocab

    asked = (state.dialog.last_question or "").lower()
    return any(m in asked for m in vocab("offer_more_markers"))


def _still_down(user_input: str | None, asked_anything_else: bool = False) -> bool:
    """The caller says it still does not work. An explicit report ("neveikia") always
    counts; a bare "ne" counts only when it is not a goodbye — "Ne, ačiū, viso gero" is a
    no to "anything else?", not a broken line (F-20: it reopened a resolved case and
    registered a technician after the goodbye)."""
    from ...contract.locale import vocab
    from ...perceive.detectors import detect_farewell, detect_restored
    from ...resolution import Outcome

    low = (user_input or "").lower()
    if any(m in low for m in vocab("restored_no")):
        return True
    if asked_anything_else:
        # „Ar dar kuo galiu padėti?" — a „ne" answers THAT („Ne, viskas susitvarkė", live
        # 2026-10-13: read as „still down", the solved call was reopened for a technician).
        return False
    return detect_restored(user_input) is Outcome.NO and not detect_farewell(user_input)
