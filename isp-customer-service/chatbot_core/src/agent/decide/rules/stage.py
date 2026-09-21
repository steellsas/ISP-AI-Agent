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

from ..plan import Action, Say, TurnPlan


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
    return scripted_layer(state, rt) or stage_plan


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
    from .closing import maybe_close_inform
    from .diagnosis import solver_drive_turn

    maybe_close_inform(state, rt, user_input)
    # The repeat guard counts the narrator's re-asks; a solver-driven turn has always
    # counted as progress (no start snapshot on this path).
    snapshot, s.turn.progress_key_at_start = s.turn.progress_key_at_start, None
    driven = solver_drive_turn(state, rt, user_input)
    if driven is not None:
        return TurnPlan(
            owner="diagnosis",
            rule="diagnosis.solver_drive",
            say=Say(kind="phrase", text=driven, committed=True, stage="diagnosis"),
        )
    s.turn.progress_key_at_start = snapshot
    from ..procedure import advance

    active = s.resolution.procedure is not None
    outcome = advance(state, rt, user_input)
    return TurnPlan(
        owner="procedure" if active else "diagnosis",
        rule=f"procedure.{outcome.kind}" if active else "diagnosis.free_reply",
        awaiting=outcome.role,
        action=Action(type="procedure_step", name="run_due_action"),
        say=Say(kind="directive", stage="diagnosis"),
    )


def _conflict_due(state: Any) -> bool:
    from ..hypothesis import due

    return due(state, "conflict") is not None


def _side_topic(state: Any) -> bool:
    """A corroborated deviation FREEZES the engine for the turn — unless a mechanic the
    turn head opened this turn (the end-confirm, a resume hold, a conflict clarify, the
    ticket dialogue) owns it."""
    if not state.turn.side_topic_active:
        return False
    return not (
        state.ticket.stage
        or state.closing.case_closed
        or _conflict_due(state)
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
    )
