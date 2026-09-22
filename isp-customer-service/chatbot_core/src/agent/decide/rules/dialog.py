"""Dialog rules that belong to no stage (§5 rows 1, 4, 6, 7, 11, 18, 19, 20)."""

from __future__ import annotations

from typing import Any

from ...contract.locale import phrase
from ..plan import Action, Say, TurnPlan


def stuck_backstop(state: Any) -> tuple[str, bool] | None:
    """Deterministic escalation (text, should_close) once the prompt-level nudge has
    failed (§5 row 18): at 3 offer the account code, at 4 close — with the
    registration an identified caller was promised (F-5). None below that."""
    from ...contract.locale import phrase

    n = state.dialog.stuck_count
    if n >= 4:
        if state.identity.customer_id:
            return (phrase("system.stuck_register"), True)
        return (phrase("system.stuck_unidentified_close"), True)
    if n >= 3:
        return (phrase("system.stuck_offer_code"), False)
    return None


def greeting(state: Any, rt: Any) -> TurnPlan | None:
    """The first turn has no caller words: the fixed opening line, with the caller's
    number looked up while it plays."""
    if state.turn.user_input is not None or state.dialog.turn_count != 0:
        return None
    state.dialog.turn_count += 1  # the opening line is the call's first turn
    return TurnPlan(
        owner="intake",
        rule="dialog.greeting",
        action=Action(type="tool", name="preflight_phone"),
        say=Say(
            kind="phrase",
            key="system.greeting",
            vars={"company_name": rt.config.company_name},
            stage="intake",
            remember_question=False,
        ),
    )


def scripted_wait_ack(state, rt) -> str | None:
    """D5 (live 2026-08-25: 'Gerai, palauksiu' cost 2.8–12 s of LLM): a bare
    work-in-progress signal while the walker awaits a CLIENT ACTION gets the
    scripted acknowledgement — zero LLM, zero latency. Anything richer (a
    question, a standing directive, an announce, a detour note) falls through
    to the narrator. Two phrases alternate so a long wait never sounds like a
    tape loop."""
    from ...perceive.detectors import INTENT_IN_PROGRESS

    s = state
    if not s.resolution.procedure or s.closing.case_closed or state.ticket.stage:
        return None
    if s.dialog.last_intent != INTENT_IN_PROGRESS or s.dialog.awaiting != "client_action":
        return None

    if state.diagnosis.pending_announcement:
        return None
    if state.dialog.resync_note or state.voice.undelivered_tail:
        return None
    d = state.turn.directives
    if d.evidence or d.recap or d.findings or d.ticket or d.ident:
        return None
    variant = (
        phrase("identification.wait_ack")
        if s.dialog.awaiting_turns % 2
        else phrase("identification.wait_ack_2")
    )
    return variant or phrase("identification.wait_ack")
