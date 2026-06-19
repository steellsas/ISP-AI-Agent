"""
LangGraph orchestration for the agent (docs/pokalbio_variklis.md §6, Phase 3.5
step 3).

Step 3.1 — the PLUMBING. A single-node StateGraph with a MemorySaver checkpointer
that delegates one turn to the existing ReactAgent engine. This proves the
LangGraph wiring (state, checkpoint, the AgentSession seam, tracing) with NO
behaviour change — the node calls the same `run_until_response`.

Step 3.2 (next) splits this into router -> address_validation -> diagnosis nodes
and migrates the conversation state into the graph. Keeping 3.1 a thin wrapper
isolates the framework integration from the node decomposition, so a regression
in either is easy to locate.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class TurnState(TypedDict, total=False):
    """Per-turn graph state. Minimal in 3.1 (the real conversation state still
    lives in the ReactAgent); the slots/messages migrate here in 3.2."""

    user_input: str | None
    reply: str | None


def build_turn_graph(engine: Any):
    """
    Compile a one-node graph that runs a single turn via `engine` (a ReactAgent),
    checkpointed with MemorySaver so 3.2 can move state into the graph.
    """

    def agent_turn(state: TurnState) -> TurnState:
        reply = engine.run_until_response(state.get("user_input"))
        return {"reply": reply}

    builder = StateGraph(TurnState)
    builder.add_node("agent", agent_turn)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=MemorySaver())
