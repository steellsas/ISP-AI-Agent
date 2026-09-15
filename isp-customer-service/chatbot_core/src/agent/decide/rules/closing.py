"""Closing rules — the turns after the case is closed (§5 row 2).

A ticket demand or a "still not working" at the goodbye reopens the case and starts
the registration; a number correction after the registration lands on the ticket;
otherwise the call ends on one short goodbye — only the first closing reply (or a real
question) is the LLM's.
"""

from __future__ import annotations

import re
from typing import Any

from ...closing_flow import maybe_finish
from ...contract import limits
from ..plan import Action, Say, TurnPlan

STAGE = "closing"


def plan(state: Any, rt: Any) -> TurnPlan | None:
    from ...perceive.detectors import detect_refuse_or_ticket, detect_restored
    from ...resolution import Outcome

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
        and detect_restored(user_input) is Outcome.NO
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
            from ...ticket_flow import fmt_phone

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
    return TurnPlan(
        owner="closing",
        rule=rule,
        say=Say(kind="phrase", key="identification.goodbye", stage=STAGE),
    )
