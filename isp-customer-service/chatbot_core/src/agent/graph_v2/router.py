"""
Router — every routing decision of the v2 graph lives in THIS file.

R2 scope (docs/ROADMAP_REFACTORING.md §3): port `route()` from agent/graph.py
unchanged — deterministic priority: case_closed -> closing, ticket stage ->
ticket, customer_id -> diagnosis, else identification. side_topic becomes a
real route target (today it is a sub-call inside diagnosis).

R3 scope: the walker guard chain (roadmap §5) migrates here group by group as
conditional-edge functions for the diagnosis subgraph.

Rules: routing functions are PURE — they read GraphState and return a node
name; no LLM calls, no tools, no mutation.
"""

from __future__ import annotations

from .state import GraphState

# Node names — the single place they are spelled out.
IDENTIFICATION = "identification"
DIAGNOSIS = "diagnosis"
SIDE_TOPIC = "side_topic"
TICKET = "ticket"
CLOSING = "closing"


def route_entry(state: GraphState) -> str:
    """Conditional entry point (ports agent/graph.py route())."""
    raise NotImplementedError("R2: port route() from agent/graph.py")
