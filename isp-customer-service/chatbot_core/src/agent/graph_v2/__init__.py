"""
LangGraph v2 — the conversation engine (the only one; docs/refactoring/).
"""

from .graph import build_graph
from .state import GraphState, TurnScratch

__all__ = ["GraphState", "TurnScratch", "build_graph"]
