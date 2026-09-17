"""
Graph assembly — add_node / add_edge / compile and NOTHING else.

    perceive -> decide -> execute -> narrate -> END

perceive reads the caller's turn, decide plans it (the policy chain), execute runs the
plan's action, narrate speaks its say. The checkpointer is injected here and the
AgentRuntime arrives per invoke as the graph context — nodes never reach for globals.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ..runtime import AgentRuntime
from .checkpoint import make_checkpointer
from .runtime import timed
from .state import GraphState


def build_graph(checkpointer: Any | None = None):
    """Compile the graph. Dependencies arrive per invoke as the AgentRuntime
    context. Without a checkpointer the call state lives in memory (tests, eval)."""
    from ..decide.node import decide_node
    from ..execute.node import execute_node, narrate_node
    from ..perceive import perceive_node

    builder = StateGraph(GraphState, context_schema=AgentRuntime)
    builder.add_node("perceive", timed("perceive", perceive_node))
    builder.add_node("decide", timed("decide", decide_node))
    builder.add_node("execute", timed("execute", execute_node))
    builder.add_node("narrate", timed("narrate", narrate_node))
    builder.set_entry_point("perceive")
    builder.add_edge("perceive", "decide")
    builder.add_edge("decide", "execute")
    builder.add_edge("execute", "narrate")
    builder.add_edge("narrate", END)
    return builder.compile(checkpointer=checkpointer or make_checkpointer())
