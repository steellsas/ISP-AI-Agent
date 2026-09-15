"""
Diagnose node — the telemetry read and the turn head's guards.

1. ensure_diagnosed — diagnose ONCE on entering the stage, so the verdict +
   resolution strategy no longer depend on the model.
2. pre_turn_guards — the deterministic turn head (decisions; M4 step 4 turns
   them into policy rules).

The caller's words were already read by the perceive node (evidence ledger,
side-topic signal).
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ....runtime import AgentRuntime
from ...runtime import node_update
from ...state import GraphState


def diagnose_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)
    return node_update(state, _diagnose(state, rt, state.turn.user_input))


def _diagnose(state: Any, rt: Any, user_input: str | None) -> None:
    from ....perception_flow import pre_turn_guards
    from ....walker_flow import ensure_diagnosed

    ensure_diagnosed(state, rt)
    # One-owner principle (live A-2, 2026-09-07): the turn head's guards run
    # BEFORE the solver/walker — solver_gate used to answer before narrate()'s
    # guards could read a safety-question answer, and "Taip taip dėl KITO
    # adreso" leaked into the walker's question. The latch prevents a double
    # run when the narrator later finishes the same turn via narrate().
    if user_input:
        # user_turn trace stays with narrate()/the solver commit — no duplicates.
        pre_turn_guards(state, rt, user_input)
        state.turn.pre_turn_head_done = True
