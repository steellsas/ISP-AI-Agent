"""
Shared node runtime — the only code nodes share besides GraphState.

Two seams:
- `narrate()` — the scoped LLM turn with token streaming (ports _run_node from
  agent/graph.py verbatim: same trace event, same stream writer contract).
- `sync_updates()` — mirrors engine.state back into GraphState after a node
  ran. This is the strangler seam: while the legacy engine still owns the
  conversation state, every turn ends by snapshotting it into the graph state,
  so checkpoints capture the full call and the entry router can stay pure.
  It disappears in R3 when state ownership moves to the graph.

Tool scopes are IMPORTED from agent/graph.py (single source) so v1 and v2 can
never drift apart while both engines are alive.
"""

from __future__ import annotations

import copy
from typing import Any

from langgraph.config import get_stream_writer

from ..graph import CLOSING_TOOLS, LOOKUP_TOOLS, TICKET_TOOLS  # noqa: F401  (re-exported)
from ..prompts import load_node_prompt
from .state import _LEGACY_FIELDS, TurnScratch

# Per-stage prompts — same loader, same files as the legacy graph.
ADDRESS_NODE_PROMPT = load_node_prompt("stages/identification")
DIAGNOSIS_NODE_PROMPT = load_node_prompt("stages/diagnosis")
CLOSING_NODE_PROMPT = load_node_prompt("stages/closing")
TICKET_NODE_PROMPT = load_node_prompt("stages/ticket")
SIDE_TOPIC_PROMPT = load_node_prompt("stages/side_topic")


def narrate(engine: Any, user_input: str | None, allowed_tools, node_prompt: str, node: str) -> str:
    """Run the engine's scoped LLM turn, streaming tokens out via the LangGraph
    stream writer (a no-op under .invoke(), live under .stream(stream_mode='custom'))
    while collecting the full reply for the checkpoint."""
    engine._active_node = node
    engine.tracer.emit("node", node=node, customer_id=engine.state.customer_id)
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
    engine._active_node = node
    engine.tracer.emit("node", node=node, customer_id=engine.state.customer_id)
    if user_input:
        engine.state.last_heard = user_input.strip()
        engine.tracer.emit("user_turn", text=user_input)
        engine.state.messages.append({"role": "user", "content": user_input})
    engine._emit_scripted_reply(reply)
    try:
        get_stream_writer()(reply)
    except Exception:  # outside a live stream (tests / .invoke) — text is in state
        pass


def sync_updates(engine: Any, *, user_input: str | None, reply: str | None) -> dict[str, Any]:
    """Snapshot engine.state (+ promoted flags) into graph-state updates."""
    # ticket_stage rides along automatically: it is an AgentState field since its
    # R3 promotion, so the legacy-field loop covers it.
    updates: dict[str, Any] = {
        name: copy.deepcopy(getattr(engine.state, name)) for name in _LEGACY_FIELDS
    }
    updates["turn"] = TurnScratch(user_input=user_input, reply=reply)
    return updates
