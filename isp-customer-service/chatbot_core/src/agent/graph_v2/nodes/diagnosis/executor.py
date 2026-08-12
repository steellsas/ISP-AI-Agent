"""
Executor node — the ONLY place tools run and tickets are registered.

Migrates here (roadmap §4): ReactAgent.ensure_action_done, _gate_tool,
_execute_tool_calls, _register_ticket_from_state, _simulate_bridge_connection.
Keeps the deterministic guarantees: tool access gate (not_identified /
id_mismatch / city_only / not_fixed) and STATE-driven idempotent ticket
creation.
"""

from __future__ import annotations

from ...state import GraphState


def executor_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over ensure_action_done + tool gate")
