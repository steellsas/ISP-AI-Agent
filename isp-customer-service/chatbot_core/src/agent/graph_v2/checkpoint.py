"""
Checkpointer factory — SqliteSaver setup for state between calls + time-travel.

R1 scope (docs/ROADMAP_REFACTORING.md §3): make_checkpointer() returning a
SqliteSaver (thread_id = session_id is already the convention in session.py).
Kept in its own file so storage choice (sqlite -> postgres later) is a
one-file swap.
"""

from __future__ import annotations


def make_checkpointer(db_path: str = "logs/graph_checkpoints.sqlite"):
    """Build the SqliteSaver used by build_graph (R1)."""
    raise NotImplementedError("R1: return SqliteSaver(db_path)")
