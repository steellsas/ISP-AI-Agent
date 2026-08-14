"""
Solver+gate node — the piloted SOLVER_DRIVE direction owns the whole turn.

Ports the legacy pipeline middle verbatim: the deterministic INFORM close
check first (a farewell after the news closes the call before any narration),
then solver_drive_turn — non-None means the solver produced the reply
end-to-end and the walker + LLM narrator are skipped
(router.route_after_solver_gate reads turn.reply).

R4 upgrade: the solver becomes the central brain for ALL verdicts (today only
no_mac_observed) and the walker becomes a procedure it invokes; a stronger
model may be configured for this node only. agent/gate.py stays pure.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from ....closing_flow import maybe_close_inform
from ...router import DIAGNOSIS
from ...runtime import sync_updates
from ...state import GraphState


def make_solver_gate_node(engine: Any):
    def solver_gate_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        maybe_close_inform(engine, user_input)
        driven = engine.solver_drive_turn(user_input)
        if driven is None:
            return {}
        engine._active_node = DIAGNOSIS
        engine.tracer.emit("node", node="diagnosis_solver", customer_id=engine.state.customer_id)
        get_stream_writer()(driven)
        return sync_updates(engine, user_input=user_input, reply=driven)

    return solver_gate_node
