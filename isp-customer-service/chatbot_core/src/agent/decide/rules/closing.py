"""Closing rules — the turns after the case is closed (§5 row 2).

A ticket demand or a "still not working" at the goodbye reopens the case and starts
the registration; a number correction after the registration lands on the ticket;
otherwise the call ends on one short goodbye — only the first closing reply (or a real
question) is the LLM's.
"""

from __future__ import annotations

import re
from typing import Any

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
        and s.resolution.procedure is not None
    ):
        s.closing.case_closed = False
        rt.tracer.emit("decision", intent="ticket_demand", action="reopen_at_closing")
        return _escalate("closing.ticket_demand_reopen")
    # A "still not working" at the goodbye contradicts a resolved close — never wave
    # it off (live 2026-09-11: "Internetas neveikia." got "Geros dienos!").
    if (
        user_input
        and s.closing.closed_reason == "resolved"
        and not s.ticket.ticket_id
        and s.resolution.procedure is not None
        and _still_down(user_input)
    ):
        s.closing.case_closed = False
        s.closing.is_complete = False
        s.resolution.procedure["escalate_reason"] = "still_down_at_closing"
        rt.tracer.emit("decision", intent="still_down", action="reopen_at_closing")
        return _escalate("closing.still_down_reopen")
    maybe_finish(state, rt, user_input)
    from ...perceive.detectors import is_real_question

    question = is_real_question(user_input)
    # After a REGISTRATION the goodbye is scripted (live 2026-08-21: the closing LLM
    # re-asked the call-back hours after the ticket was done).
    if s.ticket.ticket_id and not question:
        # A POST-registration contact correction ("skambinkite kitu numeriu 868…")
        # must land on the ticket, not vanish into the goodbye (D5, live 2026-08-25).
        digits = re.sub(r"\D", "", user_input or "")
        if len(digits) >= 6 and not s.closing.is_complete:
            from ...execute.ticket import fmt_phone

            nr = re.sub(r"[^\d+]", "", user_input or "")[:20]
            s.ticket.contact_phone = nr
            return TurnPlan(
                owner="closing",
                rule="closing.ticket_phone_amend",
                action=Action(type="append_ticket", args={"note": f"Skambinti kitu numeriu: {nr}"}),
                say=Say(
                    kind="phrase",
                    key="identification.ticket_phone_fixed",
                    vars={"phone": fmt_phone(nr)},
                    stage=STAGE,
                ),
            )
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


def _escalate(rule: str) -> TurnPlan:
    return TurnPlan(
        owner="closing",
        rule=rule,
        action=Action(type="procedure_step", name="escalate"),
        say=Say(kind="phrase", stage=STAGE),
    )


def _goodbye(rule: str) -> TurnPlan:
    """The farewell ENDS the call: the words and the hang-up are one plan (wave 1 —
    before, a goodbye-sounding reply was detected afterwards by the narrator)."""
    return TurnPlan(
        owner="closing",
        rule=rule,
        action=Action(type="close", name="registered", args={"complete": True}),
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
        s.closing.is_complete = True


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
    ):
        return
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    # INFORM mode: an outage was flagged, OR we identified + diagnosed but there is no
    # resolution strategy to walk (active_outage, billing_suspended, generic inform).
    # A live strategy (foreign_mac, dead-router, client-side) keeps s.resolution set
    # and is handled by the walker instead — never closed here.
    inform_mode = s.diagnosis.outage_reported or (
        s.resolution.procedure is None and bool(s.diagnosis.verdicts)
    )
    if not inform_mode:
        return
    from ...perceive.detectors import detect_farewell

    if detect_farewell(user_input):
        s.closing.case_closed = True
        s.closing.closed_reason = (
            "outage"
            if (s.diagnosis.outage_reported or verdict_flag(reason, "inform") == "outage")
            else "inform"
        )
        s.closing.is_complete = True  # caller already said goodbye — end on ONE farewell
        # Observability: the close moment was invisible in the trace (this made a
        # stuck-close analysis needlessly hard) — record it.
        rt.tracer.emit(
            "decision", intent="inform_close", action="close", to=s.closing.closed_reason
        )


def _still_down(user_input: str | None) -> bool:
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
    return detect_restored(user_input) is Outcome.NO and not detect_farewell(user_input)
