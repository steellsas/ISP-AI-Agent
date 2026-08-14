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

from ...state import GraphState


def make_walker_node(engine: Any):
    def walker_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        engine._advance_resolution(user_input)
        engine._shadow_solve(user_input)
        return {}

    return walker_node
