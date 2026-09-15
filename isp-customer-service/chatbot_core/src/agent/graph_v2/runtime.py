"""
Shared node runtime — the only code nodes share besides GraphState.

Two seams:
- `narrate()` — the scoped LLM turn with token streaming (node trace event +
  stream writer contract).
- `node_update()` — the node contract: a node works on a copy of the graph
  state and returns the full state as its update, so the checkpoint is the only
  state between nodes and between turns.
- `narrator()` — the LLM narrator loop (ReactAgent) for a node run.

Tool scopes live in tool_scopes.py (re-exported here for the nodes).
"""

from __future__ import annotations

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


def narrate(
    state: Any,
    rt: Any,
    user_input: str | None,
    allowed_tools,
    node_prompt: str,
    node: str,
    planned: bool = False,
) -> str:
    """Run the engine's scoped LLM turn, streaming tokens out via the LangGraph
    stream writer (a no-op under .invoke(), live under .stream(stream_mode='custom'))
    while collecting the full reply for the checkpoint."""
    state.turn.active_node = node
    rt.tracer.emit("node", node=node, customer_id=state.identity.customer_id)
    writer = get_stream_writer()
    parts: list[str] = []
    for token in narrator(state, rt).run_turn_scoped_stream(
        user_input, allowed_tools, node_prompt, planned
    ):
        writer(token)
        parts.append(token)
    return "".join(parts)


def speak_scripted(state: Any, rt: Any, node: str, user_input: str | None, reply: str) -> None:
    """A SCRIPTED node reply must reach the transport too (live 2026-08-25: the
    post-registration goodbye returned in the state update only — zero tokens
    streamed — and the call ended in dead silence, three caller turns in a
    row). Mirrors narrate()'s surface for an engine-composed line: node event,
    history, trace, and the stream writer."""
    state.turn.active_node = node
    rt.tracer.emit("node", node=node, customer_id=state.identity.customer_id)
    if user_input:
        state.dialog.last_heard = user_input.strip()
        rt.tracer.emit("user_turn", text=user_input)
        state.messages.append({"role": "user", "content": user_input})
    narrator(state, rt)._emit_scripted_reply(reply)
    # W0-D (live 2026-08-25: "Geros dienos!" said 3×): a scripted goodbye must
    # END the call like an LLM one — the hang-up detector ran only on the LLM
    # path, so every trailing garbled turn earned a fresh goodbye.
    from ..closing_flow import maybe_end_on_goodbye

    maybe_end_on_goodbye(state, rt, reply)
    try:
        get_stream_writer()(reply)
    except Exception:  # outside a live stream (tests / .invoke) — text is in state
        pass


def node_update(state: GraphState, reply: str | None = None) -> dict[str, Any]:
    """The node contract: a node works on its own copy of the state and returns
    the whole state as its update; a non-None `reply` is the turn's reply."""
    if reply is not None:
        state.turn.reply = reply
    return {name: getattr(state, name) for name in GraphState.model_fields}


def narrator(state: GraphState, rt: Any):
    """The LLM narrator loop (ReactAgent) for one node run on `state`."""
    from ..react_agent import ReactAgent

    return ReactAgent(state, rt)
