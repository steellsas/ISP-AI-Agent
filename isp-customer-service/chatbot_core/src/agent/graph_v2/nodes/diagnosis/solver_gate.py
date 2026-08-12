"""
Solver+gate node — hypothesis and next action, kept safe by the gate.

Migrates here (roadmap §4): ReactAgent.solver_drive_turn, _drive,
_shadow_solve, _build_solver_context. agent/gate.py stays pure and unchanged.

R4 upgrade: the solver becomes the central brain for ALL verdicts (today only
no_mac_observed) and the walker becomes a procedure it invokes; a stronger
model may be configured for this node only.
"""

from __future__ import annotations

from ...state import GraphState


def solver_gate_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over solver_drive_turn/_shadow_solve")
