"""
Walker node — deterministic strategy step walking (HOLD / advance / goto).

Thin wrapper: _advance_resolution (the walker with its 15-guard chain) plus
_shadow_solve (solver logging next to the walker's move, SOLVER_SHADOW only).

R3 follow-up (roadmap §5): the guard chain migrates out of
ReactAgent._walk_resolution into walker-module functions in groups of 2-3,
with golden parity runs between groups. The step sequencer (next_step_id,
detectors) stays pure in agent/resolution.py.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ....runtime import AgentRuntime
from ...runtime import node_update
from ...state import GraphState


def walker_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ....solver_flow import shadow_solve
    from ....walker_flow import advance_resolution

    rt = runtime.context
    state = state.model_copy(deep=True)

    def body() -> None:
        user_input = state.turn.user_input
        advance_resolution(state, rt, user_input)
        shadow_solve(state, rt, user_input)

    return node_update(state, body())
