"""
Graph assembly — add_node / add_edge / compile and NOTHING else.

All logic lives in nodes/ (one node = one file) and router.py; this file only
wires them together, so the whole flow is readable in one screen.

R2 scope (docs/ROADMAP_REFACTORING.md §3): build_graph(engine) returns the
compiled v2 graph wired to thin node wrappers; session.py selects it via
AGENT_ENGINE=v2. Dependencies (engine, tracer, config) are injected here via
closures/factories — nodes never reach for globals.

R1 remainder: swap MemorySaver -> SqliteSaver (checkpoint.py).
"""

from __future__ import annotations


def build_graph(engine, checkpointer=None):
    """Assemble and compile the v2 StateGraph (R2)."""
    raise NotImplementedError("R2: assemble nodes/ + router.py into a StateGraph")
