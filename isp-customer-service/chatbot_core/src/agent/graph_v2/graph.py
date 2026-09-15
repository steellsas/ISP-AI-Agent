"""
Graph assembly — add_node / add_edge / compile and NOTHING else.

All logic lives in nodes/ (one node = one file) and router.py; this file only
wires them together, so the whole flow is readable in one screen.
The checkpointer is injected here and the AgentRuntime arrives per invoke as
the graph context — nodes never reach for globals.

Current shape: perceive -> decide -> END when a policy rule owned the turn, else
router -> identification | ticket | DIAGNOSIS SUBGRAPH (diagnose -> side_topic |
solver_gate -> walker -> executor -> narrator) -> END, checkpointed per session.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ..runtime import AgentRuntime
from .checkpoint import make_checkpointer
from .nodes.diagnosis import make_diagnosis_graph
from .nodes.identification import identification_node
from .nodes.ticket import ticket_node
from .router import (
    ADDRESS_VALIDATION,
    DECIDE,
    DIAGNOSIS,
    ENTRY_TARGETS,
    PERCEIVE,
    TICKET_REGISTRATION,
    route_after_decide,
)
from .state import GraphState


def build_graph(checkpointer: Any | None = None):
    """Compile the graph. Dependencies arrive per invoke as the AgentRuntime
    context. Without a checkpointer the call state lives in memory (tests, eval)."""
    from ..decide.node import decide_node
    from ..perceive import perceive_node

    builder = StateGraph(GraphState, context_schema=AgentRuntime)
    builder.add_node(PERCEIVE, perceive_node)
    builder.add_node(DECIDE, decide_node)
    builder.add_node(ADDRESS_VALIDATION, identification_node)
    builder.add_node(DIAGNOSIS, make_diagnosis_graph())
    builder.add_node(TICKET_REGISTRATION, ticket_node)
    builder.set_entry_point(PERCEIVE)
    builder.add_edge(PERCEIVE, DECIDE)
    targets = {name: name for name in ENTRY_TARGETS}
    builder.add_conditional_edges(DECIDE, route_after_decide, {**targets, "end": END})
    for name in ENTRY_TARGETS:
        builder.add_edge(name, END)
    return builder.compile(checkpointer=checkpointer or make_checkpointer())
