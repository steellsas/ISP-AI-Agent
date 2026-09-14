"""
Shared node runtime — the only code nodes share besides GraphState.

Two seams:
- `narrate()` — the scoped LLM turn with token streaming (node trace event +
  stream writer contract).
- `run_on_state()` — the node contract: the node body runs on a working copy
  of the graph state and the node returns the full state as its update, so the
  checkpoint is the only state between nodes and between turns.

Tool scopes live in tool_scopes.py (re-exported here for the nodes).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.config import get_stream_writer

from ..prompts import load_node_prompt
from .state import GraphState
from .tool_scopes import CLOSING_TOOLS, LOOKUP_TOOLS, TICKET_TOOLS  # noqa: F401  (re-exported)

# Per-stage prompts.
ADDRESS_NODE_PROMPT = load_node_prompt("stages/identification")
DIAGNOSIS_NODE_PROMPT = load_node_prompt("stages/diagnosis")
CLOSING_NODE_PROMPT = load_node_prompt("stages/closing")
TICKET_NODE_PROMPT = load_node_prompt("stages/ticket")
SIDE_TOPIC_PROMPT = load_node_prompt("stages/side_topic")


def narrate(engine: Any, user_input: str | None, allowed_tools, node_prompt: str, node: str) -> str:
    """Run the engine's scoped LLM turn, streaming tokens out via the LangGraph
    stream writer (a no-op under .invoke(), live under .stream(stream_mode='custom'))
    while collecting the full reply for the checkpoint."""
    engine.state.turn.active_node = node
    engine.tracer.emit("node", node=node, customer_id=engine.state.identity.customer_id)
    writer = get_stream_writer()
    parts: list[str] = []
    for token in engine.run_turn_scoped_stream(user_input, allowed_tools, node_prompt):
        writer(token)
        parts.append(token)
    return "".join(parts)


def speak_scripted(engine: Any, node: str, user_input: str | None, reply: str) -> None:
    """A SCRIPTED node reply must reach the transport too (live 2026-08-25: the
    post-registration goodbye returned via sync_updates only — zero tokens
    streamed — and the call ended in dead silence, three caller turns in a
    row). Mirrors narrate()'s surface for an engine-composed line: node event,
    history, trace, and the stream writer."""
    engine.state.turn.active_node = node
    engine.tracer.emit("node", node=node, customer_id=engine.state.identity.customer_id)
    if user_input:
        engine.state.dialog.last_heard = user_input.strip()
        engine.tracer.emit("user_turn", text=user_input)
        engine.state.messages.append({"role": "user", "content": user_input})
    engine._emit_scripted_reply(reply)
    # W0-D (live 2026-08-25: "Geros dienos!" said 3×): a scripted goodbye must
    # END the call like an LLM one — the hang-up detector ran only on the LLM
    # path, so every trailing garbled turn earned a fresh goodbye.
    from ..closing_flow import maybe_end_on_goodbye

    maybe_end_on_goodbye(engine, reply)
    try:
        get_stream_writer()(reply)
    except Exception:  # outside a live stream (tests / .invoke) — text is in state
        pass


def run_on_state(engine: Any, state: GraphState, body: Callable[[], str | None]) -> dict[str, Any]:
    """Run a node body on a working copy of `state` and return the full update.

    The engine's flows read and write `engine.state`; it is set to a deep copy of
    the node's input state, so nothing outlives the node except what it returns.
    A non-None result of `body` is the turn's reply."""
    engine.state = state.model_copy(deep=True)
    reply = body()
    if reply is not None:
        engine.state.turn.reply = reply
    return {name: getattr(engine.state, name) for name in GraphState.model_fields}
