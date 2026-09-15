"""
Execute node — runs the TurnPlan's action through the engine (tools via the gateway,
procedure step effects, ticket registration); its words wait for narrate.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ..graph_v2.runtime import node_update
from ..graph_v2.state import GraphState
from ..runtime import AgentRuntime


def execute_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ..decide.plan import TurnPlan
    from .actions import run_action

    rt = runtime.context
    state = state.model_copy(deep=True)
    state.turn.action_text = run_action(state, rt, TurnPlan(**state.turn.plan))
    return node_update(state)


def narrate_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ..decide.plan import TurnPlan
    from .say import speak

    rt = runtime.context
    state = state.model_copy(deep=True)
    reply = speak(state, rt, TurnPlan(**state.turn.plan), state.turn.action_text)
    return node_update(state, reply)
