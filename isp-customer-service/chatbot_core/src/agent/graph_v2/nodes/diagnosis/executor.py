"""
Executor node — deterministic ACTION/ESCALATE execution before narration.

Thin wrapper over ensure_action_done: an ACTION step reached by the caller's
reply runs deterministically BEFORE the LLM narrates — the engine binds +
resets + re-verifies and sets case_closed, so the model only PHRASES the
verified result (no model-invoked update_mac).

R3 follow-up (roadmap §4): the tool gateway (agent/tooling), the tool-call loop and
_register_ticket_from_state migrate here so this file is the ONLY place tools
run and tickets are registered.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ....runtime import AgentRuntime
from ...runtime import run_on_state
from ...state import GraphState


def executor_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    engine = runtime.context.engine

    def body() -> None:
        engine.ensure_action_done()

    return run_on_state(engine, state, body)
