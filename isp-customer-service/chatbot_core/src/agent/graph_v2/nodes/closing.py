"""
Closing node — one short goodbye matched to closed_reason, then hang-up.

maybe_finish (agent/closing_flow.py, R3 extraction) decides whether to hang
up (farewell or second closing turn sets is_complete) BEFORE the tools-less
narration.

R3 follow-up (roadmap §4): end_session (call record + persistence).
"""

from __future__ import annotations

from typing import Any

from ...closing_flow import maybe_finish
from ..router import CLOSING
from ..runtime import CLOSING_NODE_PROMPT, CLOSING_TOOLS, narrate, speak_scripted, sync_updates
from ..state import GraphState


def make_closing_node(engine: Any):
    def closing_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        # A ticket demand at the goodbye reopens the case (live 2026-08-13:
        # "Dar prašau, žegistruokit gedimą…" got "gražios dienos!" and the
        # caller left with ticket=None) — the registration dialogue starts
        # instead of the farewell.
        from ...resolution import detect_refuse_or_ticket

        s = engine.state
        if (
            user_input
            and detect_refuse_or_ticket(user_input) == "demand"
            and not s.ticket_id
            and s.resolution is not None
        ):
            s.case_closed = False
            engine.tracer.emit("decision", intent="ticket_demand", action="reopen_at_closing")
            reply = engine._drive_escalate(None)
            if reply:  # narrator mode leaves the intro to the LLM (directive set)
                speak_scripted(engine, CLOSING, user_input, reply)
                return sync_updates(engine, user_input=user_input, reply=reply)
            reply = narrate(engine, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
            return sync_updates(engine, user_input=user_input, reply=reply)
        maybe_finish(engine, user_input)
        # After a REGISTRATION the goodbye is scripted (live 2026-08-21: the
        # closing LLM re-asked the call-back hours after the ticket was done).
        # The LLM speaks only for a real question, or ONCE to ask back about
        # secondary problems the caller mentioned mid-call.
        from ...identification import phrase
        from ...resolution import is_real_question

        if s.ticket_id and not is_real_question(user_input):
            # D5 (live 2026-08-25): a POST-registration contact correction
            # ("skambinkite kitu numeriu 868…") must land on the ticket, not
            # vanish into the goodbye — the worker would call a dead number.
            import re as _re

            digits = _re.sub(r"\D", "", user_input or "")
            if len(digits) >= 6 and not s.is_complete:
                from ...ticket_flow import amend_ticket_note, fmt_phone

                nr = _re.sub(r"[^\d+]", "", user_input or "")[:20]
                s.contact_phone = nr
                noted = amend_ticket_note(engine, f"Skambinti kitu numeriu: {nr}")
                engine.tracer.emit(
                    "decision",
                    intent="ticket_amend",
                    action="phone_noted" if noted else "note_failed",
                )
                reply = phrase("ticket_phone_fixed", nr=fmt_phone(nr))
                speak_scripted(engine, CLOSING, user_input, reply)
                return sync_updates(engine, user_input=user_input, reply=reply)
            if s.secondary_problems and not getattr(engine, "_secondary_asked", False):
                engine._secondary_asked = True  # the facts directive carries the list
            else:
                reply = phrase("goodbye")
                speak_scripted(engine, CLOSING, user_input, reply)
                return sync_updates(engine, user_input=user_input, reply=reply)
        reply = narrate(engine, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
        return sync_updates(engine, user_input=user_input, reply=reply)

    return closing_node
