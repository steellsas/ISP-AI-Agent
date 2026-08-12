"""
Diagnosis subgraph — the legacy 9-step in-node pipeline made explicit (R3).

    diag_diagnose ──(side_topic_active?)──> diag_side_topic ──> END
          │
          └──> diag_solver_gate ──(turn.reply set? = solver drove)──> END
                     │
                     └──> diag_walker ──> diag_executor ──> diag_narrator ──> END

Engine-call ORDER is identical to the legacy diagnosis() node — only the
control flow moved from Python if/returns into graph edges, so every branch
is now visible, checkpointed and individually testable. Assembly only; the
logic lives in the sibling node files and router.py.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ...router import (
    DIAG_DIAGNOSE,
    DIAG_EXECUTOR,
    DIAG_NARRATOR,
    DIAG_SIDE_TOPIC,
    DIAG_SOLVER_GATE,
    DIAG_WALKER,
    route_after_diagnose,
    route_after_solver_gate,
)
from ...state import GraphState
from ..side_topic import make_side_topic_node
from .diagnose import make_diagnose_node
from .executor import make_executor_node
from .narrator import make_narrator_node
from .solver_gate import make_solver_gate_node
from .walker import make_walker_node


def make_diagnosis_graph(engine: Any):
    """Compile the diagnosis subgraph (no checkpointer — inherits the parent's)."""
    builder = StateGraph(GraphState)
    builder.add_node(DIAG_DIAGNOSE, make_diagnose_node(engine))
    builder.add_node(DIAG_SIDE_TOPIC, make_side_topic_node(engine))
    builder.add_node(DIAG_SOLVER_GATE, make_solver_gate_node(engine))
    builder.add_node(DIAG_WALKER, make_walker_node(engine))
    builder.add_node(DIAG_EXECUTOR, make_executor_node(engine))
    builder.add_node(DIAG_NARRATOR, make_narrator_node(engine))
    builder.set_entry_point(DIAG_DIAGNOSE)
    builder.add_conditional_edges(
        DIAG_DIAGNOSE,
        route_after_diagnose,
        {DIAG_SIDE_TOPIC: DIAG_SIDE_TOPIC, DIAG_SOLVER_GATE: DIAG_SOLVER_GATE},
    )
    builder.add_conditional_edges(
        DIAG_SOLVER_GATE,
        route_after_solver_gate,
        {"end": END, DIAG_WALKER: DIAG_WALKER},
    )
    builder.add_edge(DIAG_WALKER, DIAG_EXECUTOR)
    builder.add_edge(DIAG_EXECUTOR, DIAG_NARRATOR)
    builder.add_edge(DIAG_SIDE_TOPIC, END)
    builder.add_edge(DIAG_NARRATOR, END)
    return builder.compile()
