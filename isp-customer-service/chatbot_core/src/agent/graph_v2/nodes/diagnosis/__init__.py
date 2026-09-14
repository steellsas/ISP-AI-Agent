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

from ....runtime import AgentRuntime
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
from ..side_topic import side_topic_node
from .diagnose import diagnose_node
from .executor import executor_node
from .narrator import narrator_node
from .solver_gate import solver_gate_node
from .walker import walker_node


def make_diagnosis_graph():
    """Compile the diagnosis subgraph (no checkpointer — inherits the parent's)."""
    builder = StateGraph(GraphState, context_schema=AgentRuntime)
    builder.add_node(DIAG_DIAGNOSE, diagnose_node)
    builder.add_node(DIAG_SIDE_TOPIC, side_topic_node)
    builder.add_node(DIAG_SOLVER_GATE, solver_gate_node)
    builder.add_node(DIAG_WALKER, walker_node)
    builder.add_node(DIAG_EXECUTOR, executor_node)
    builder.add_node(DIAG_NARRATOR, narrator_node)
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
