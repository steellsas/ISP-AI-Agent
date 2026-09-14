"""
Shared node runtime — the only code nodes share besides GraphState.

Two seams:
- `narrate()` — the scoped LLM turn with token streaming (node trace event +
  stream writer contract).
- `sync_updates()` — mirrors engine.state back into GraphState after a node
  ran, so checkpoints capture the full call and the entry router can stay pure.
  It disappears when nodes return their own updates (M1 step 5).

Tool scopes live in tool_scopes.py (re-exported here for the nodes).
"""

from __future__ import annotations

import copy
from typing import Any

from langgraph.config import get_stream_writer

from ..prompts import load_node_prompt
from .state import STATE_GROUPS, TurnScratch
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
    engine._active_node = node
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
    engine._active_node = node
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


def sync_updates(engine: Any, *, user_input: str | None, reply: str | None) -> dict[str, Any]:
    """Snapshot engine.state into graph-state updates."""
    updates: dict[str, Any] = {
        name: copy.deepcopy(getattr(engine.state, name)) for name in STATE_GROUPS
    }
    updates["turn"] = TurnScratch(user_input=user_input, reply=reply)
    return updates
