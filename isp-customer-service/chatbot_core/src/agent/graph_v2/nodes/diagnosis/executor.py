"""
Executor node — deterministic ACTION/ESCALATE execution before narration.

Thin wrapper over ensure_action_done: an ACTION step reached by the caller's
reply runs deterministically BEFORE the LLM narrates — the engine binds +
resets + re-verifies and sets case_closed, so the model only PHRASES the
verified result (no model-invoked update_mac).

R3 follow-up (roadmap §4): _gate_tool, _execute_tool_calls and
_register_ticket_from_state migrate here so this file is the ONLY place tools
run and tickets are registered.
"""

from __future__ import annotations

from typing import Any

from ...state import GraphState


def make_executor_node(engine: Any):
    def executor_node(state: GraphState) -> dict[str, Any]:
        engine.ensure_action_done()
        return {}

    return executor_node
