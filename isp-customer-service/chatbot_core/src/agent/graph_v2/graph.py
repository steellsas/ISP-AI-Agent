"""
Graph assembly — add_node / add_edge / compile and NOTHING else.

All logic lives in nodes/ (one node = one file) and router.py; this file only
wires them together, so the whole flow is readable in one screen.
Dependencies (engine, checkpointer) are injected here — nodes never reach for
globals.

Current shape (R2 thin-wrapper phase — behaviour identical to agent/graph.py):
entry router -> one of 4 nodes -> END, checkpointed per session. The
diagnosis subgraph split follows in R3.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .checkpoint import make_checkpointer
from .nodes.closing import make_closing_node
from .nodes.diagnosis import make_diagnosis_node
from .nodes.identification import make_identification_node
from .nodes.ticket import make_ticket_node
from .router import (
    ADDRESS_VALIDATION,
    CLOSING,
    DIAGNOSIS,
    ENTRY_TARGETS,
    TICKET_REGISTRATION,
    route_entry,
)
from .state import GraphState


def build_graph(engine: Any, checkpointer: Any | None = None):
    """Compile the v2 graph around `engine` (a ReactAgent)."""
    builder = StateGraph(GraphState)
    builder.add_node(ADDRESS_VALIDATION, make_identification_node(engine))
    builder.add_node(DIAGNOSIS, make_diagnosis_node(engine))
    builder.add_node(TICKET_REGISTRATION, make_ticket_node(engine))
    builder.add_node(CLOSING, make_closing_node(engine))
    builder.set_conditional_entry_point(route_entry, {name: name for name in ENTRY_TARGETS})
    for name in ENTRY_TARGETS:
        builder.add_edge(name, END)
    return builder.compile(checkpointer=checkpointer or make_checkpointer())
