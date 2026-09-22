"""The stage families — what a turn no dialogue rule owned does (§5 rows 12, 15-17, 20).

Unidentified: the identification narrator speaks (its scripted ladder first).
Identified: the first diagnosis runs once; a corroborated side topic freezes the engine
for one answer; otherwise the inform close check, then the solver drive (evidence-led
packs) — its reply is the turn — or the procedure walks from the caller's answer, the
due step action runs, and the diagnosis narrator speaks (its scripted replies first).

The solver drive still calls the LLM solver and the gated tools inside decide; M4
steps 6-8 split it into the procedure runner, the hypothesis state machine and plan
actions.
"""

from __future__ import annotations

from typing import Any

from ..plan import Say, TurnPlan


def plan(state: Any, rt: Any) -> TurnPlan:
    """The stage families FIRST (they move the procedure), then the scripted reply
    layer — so the engine's own words match the position the turn just reached. A
    solver-driven turn already has its words and takes no layer.

    Wave 1: the layer used to run inside the NARRATOR (execute/say.scripted_exit),
    which left the narrator planning, closing calls and registering tickets."""
    from .reply import scripted_layer

    stage_plan = _stage_plan(state, rt)
    if stage_plan.say.committed:
        return stage_plan
    scripted = scripted_layer(state, rt)
    if scripted is None:
        return stage_plan
    # Wave 3: the fault path belongs to the Case. The dialogue families (identification,
    # the ticket ladder, closing, the stuck backstop) keep their scripted words, but a
    # diagnosis-side script may no longer overwrite what the Case decided — it silently
    # replaced a bind announcement and the engine walked on as if it had been said (full
    # eval, S1).
    if str(stage_plan.rule).startswith("case.") and _is_fault_script(scripted.rule):
        return stage_plan
    return scripted


def _is_fault_script(rule: str) -> bool:
    """Scripted words that used to come from the evidence drive and the walker.

    Identification is NOT one of them: its scripted ladder (the holder clarification, the
    address confirmations) is deterministic for privacy reasons and outranks the fault path
    (full eval: I6, where the Case swallowed „sutartis registruota kitu vardu").
    """
    return str(rule).split(".", 1)[0] in ("diagnosis", "procedure")


def _stage_plan(state: Any, rt: Any) -> TurnPlan:
    s = state
    user_input = s.turn.user_input
    if not s.identity.customer_id:
        return TurnPlan(
            owner="identification",
            rule="identification.free_reply",
            say=Say(kind="directive", stage="intake"),
        )
    from ...execute.diagnosis import ensure_diagnosed

    ensure_diagnosed(state, rt)
    if _side_topic(s):
        return TurnPlan(
            owner="side_topic",
            rule="side_topic.answer",
            say=Say(kind="directive", stage="side_topic"),
        )
    from . import case_rule
    from .closing import maybe_close_inform

    maybe_close_inform(state, rt, user_input)
    # Wave 3: ONE driver on the fault path. The evidence drive, the LLM solver and the
    # walker used to share it with handover rules between them (review finding N).
    planned = case_rule.plan(state, rt)
    if planned is not None:
        return planned
    return TurnPlan(
        owner="diagnosis",
        rule="diagnosis.free_reply",
        say=Say(kind="directive", stage="diagnosis"),
    )


def _side_topic(state: Any) -> bool:
    """A corroborated deviation FREEZES the engine for the turn — unless a mechanic the
    turn head opened this turn (the end-confirm, a resume hold, a conflict clarify, the
    ticket dialogue) owns it."""
    if not state.turn.side_topic_active:
        return False
    return not (
        state.ticket.stage
        or state.closing.case_closed
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
    )
