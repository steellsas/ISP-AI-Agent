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
from langgraph.runtime import Runtime

from ....closing_flow import maybe_close_inform
from ....runtime import AgentRuntime
from ...router import DIAGNOSIS
from ...runtime import node_update
from ...state import GraphState


def solver_gate_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)
    return node_update(state, _solver_gate(state, rt, state.turn.user_input))


def _solver_gate(state: Any, rt: Any, user_input: str | None) -> str | None:
    from ....solver_flow import solver_drive_turn

    maybe_close_inform(state, rt, user_input)
    driven = solver_drive_turn(state, rt, user_input)
    if driven is None:
        return None
    # narrate() will not run this turn — consume the deterministic-head
    # latch here so the NEXT turn's narrate does not skip its head.
    state.turn.pre_turn_head_done = False
    state.turn.active_node = DIAGNOSIS
    rt.tracer.emit("node", node="diagnosis_solver", customer_id=state.identity.customer_id)
    get_stream_writer()(driven)
    return driven
