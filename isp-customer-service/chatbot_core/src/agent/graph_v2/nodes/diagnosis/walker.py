"""
Walker node — deterministic strategy step walking (HOLD / advance / goto).

Migrates here (roadmap §4): ReactAgent._walk_resolution, every _advance_*,
_detect_confirm, _route_to, _goto_step, _turn_may_advance. The step sequencer
(next_step_id, detectors) stays pure in agent/resolution.py.

The 15-guard chain (roadmap §5) does NOT move into this file — each guard
becomes a conditional-edge function in router.py, ported in groups of 2-3
with golden tests between groups.
"""

from __future__ import annotations

from ...state import GraphState


def walker_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over _walk_resolution")
