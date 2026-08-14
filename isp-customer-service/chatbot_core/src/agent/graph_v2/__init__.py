"""
LangGraph v2 — the refactored graph engine (docs/ROADMAP_REFACTORING.md).

Grown alongside the legacy engine behind the AGENT_ENGINE switch (strangler
pattern): R1 state migration -> R2 thin node wrappers -> R3 logic move.
"""

from .graph import build_graph
from .state import GraphState, TurnScratch

__all__ = ["GraphState", "TurnScratch", "build_graph"]
