"""
Closing node — one short goodbye matched to closed_reason, then hang-up.

maybe_finish (agent/closing_flow.py, R3 extraction) decides whether to hang
up (farewell or second closing turn sets is_complete) BEFORE the tools-less
narration.

R3 follow-up (roadmap §4): end_session (call record + persistence).
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ...closing_flow import maybe_finish
from ...runtime import AgentRuntime
from ..router import CLOSING
from ..runtime import CLOSING_NODE_PROMPT, CLOSING_TOOLS, narrate, node_update, speak_scripted
from ..state import GraphState


def closing_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)
    return node_update(state, _closing(state, rt, state.turn.user_input))


def _closing(state: Any, rt: Any, user_input: str | None) -> str:
    # A ticket demand at the goodbye reopens the case (live 2026-08-13:
    # "Dar prašau, žegistruokit gedimą…" got "gražios dienos!" and the
    # caller left with ticket=None) — the registration dialogue starts
    # instead of the farewell.
    from ...resolution import detect_refuse_or_ticket
    from ...solver_flow import drive_escalate

    s = state
    if (
        user_input
        and detect_refuse_or_ticket(user_input) == "demand"
        and not s.ticket.ticket_id
        and s.resolution.procedure is not None
    ):
        s.closing.case_closed = False
        rt.tracer.emit("decision", intent="ticket_demand", action="reopen_at_closing")
        reply = drive_escalate(state, rt, None)
        if reply:  # narrator mode leaves the intro to the LLM (directive set)
            speak_scripted(state, rt, CLOSING, user_input, reply)
            return reply
        reply = narrate(state, rt, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
        return reply
    # A "still not working" at the goodbye contradicts a resolved close —
    # never wave it off (live 2026-09-11: "Internetas neveikia." got
    # "Geros dienos!"). Reopen and register instead of celebrating.
    from ...resolution import Outcome, detect_restored

    if (
        user_input
        and s.closing.closed_reason == "resolved"
        and not s.ticket.ticket_id
        and s.resolution.procedure is not None
        and detect_restored(user_input) is Outcome.NO
    ):
        s.closing.case_closed = False
        s.closing.is_complete = False
        s.resolution.procedure["escalate_reason"] = (
            "Klientas atsisveikinant pasakė, kad internetas vis tiek neveikia."
        )
        rt.tracer.emit("decision", intent="still_down", action="reopen_at_closing")
        reply = drive_escalate(state, rt, None)
        if reply:
            speak_scripted(state, rt, CLOSING, user_input, reply)
            return reply
        reply = narrate(state, rt, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
        return reply
    maybe_finish(state, rt, user_input)
    # After a REGISTRATION the goodbye is scripted (live 2026-08-21: the
    # closing LLM re-asked the call-back hours after the ticket was done).
    # The LLM speaks only for a real question, or ONCE to ask back about
    # secondary problems the caller mentioned mid-call.
    from ...identification import phrase
    from ...resolution import is_real_question

    if s.ticket.ticket_id and not is_real_question(user_input):
        # D5 (live 2026-08-25): a POST-registration contact correction
        # ("skambinkite kitu numeriu 868…") must land on the ticket, not
        # vanish into the goodbye — the worker would call a dead number.
        import re as _re

        digits = _re.sub(r"\D", "", user_input or "")
        if len(digits) >= 6 and not s.closing.is_complete:
            from ...ticket_flow import amend_ticket_note, fmt_phone

            nr = _re.sub(r"[^\d+]", "", user_input or "")[:20]
            s.ticket.contact_phone = nr
            noted = amend_ticket_note(state, rt, f"Skambinti kitu numeriu: {nr}")
            rt.tracer.emit(
                "decision",
                intent="ticket_amend",
                action="phone_noted" if noted else "note_failed",
            )
            reply = phrase("ticket_phone_fixed", nr=fmt_phone(nr))
            speak_scripted(state, rt, CLOSING, user_input, reply)
            return reply
        if s.intake.secondary_problems and not state.closing.secondary_problems_asked:
            state.closing.secondary_problems_asked = True  # the facts directive carries the list
        else:
            reply = phrase("goodbye")
            speak_scripted(state, rt, CLOSING, user_input, reply)
            return reply
    # Closing wave block 4 (live 2026-09-08: three near-identical
    # "Džiaugiuosi… routeris buvo pakibęs…" improvisations after the
    # goodbye moment): the FIRST closing reply may be the LLM's warm,
    # personalised close — every trailing non-question turn gets the
    # short scripted goodbye instead of a fresh re-explanation.
    if not is_real_question(user_input) and (s.closing.is_complete or s.closing.closing_turns >= 1):
        reply = phrase("goodbye")
        speak_scripted(state, rt, CLOSING, user_input, reply)
        return reply
    reply = narrate(state, rt, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
    return reply
