"""
Diagnose node — the telemetry read: diagnose ONCE on entering the stage, so the
verdict + resolution strategy no longer depend on the model.

The caller's words were already read by the perceive node and the turn head's
families ran in decide (one-owner principle, live A-2 2026-09-07: the head reads a
safety-question answer before the solver/walker can consume it).
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
    from ....walker_flow import ensure_diagnosed

    ensure_diagnosed(state, rt)
