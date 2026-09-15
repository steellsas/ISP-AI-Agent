"""
Decide node — runs the policy chain on the perceived turn. When a rule owns the turn
it records the TurnPlan, runs its action and speaks its say; otherwise the stage nodes
take the turn (families not ported yet).
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ..graph_v2.runtime import node_update
from ..graph_v2.state import GraphState
from ..runtime import AgentRuntime


def decide_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ..execute.actions import run_action
    from ..execute.say import speak
    from .policy import plan_turn

    rt = runtime.context
    state = state.model_copy(deep=True)
    plan = plan_turn(state, rt)
    if plan is None:
        return node_update(state)
    state.turn.plan = plan.model_dump(mode="json")
    action_text = run_action(state, rt, plan)
    return node_update(state, speak(state, rt, plan, action_text))
