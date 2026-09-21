"""
Decide node — runs the policy chain on the perceived turn and records its TurnPlan.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ..graph_v2.runtime import node_update
from ..graph_v2.state import GraphState
from ..runtime import AgentRuntime


def decide_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from .gate import check_plan
    from .plan import record
    from .policy import plan_turn

    rt = runtime.context
    state = state.model_copy(deep=True)
    if state.turn.plan is not None:  # a second pass: the previous plan's action ran
        state.turn.plan_hops += 1
    record(state, check_plan(state, rt, plan_turn(state, rt)))
    return node_update(state)
