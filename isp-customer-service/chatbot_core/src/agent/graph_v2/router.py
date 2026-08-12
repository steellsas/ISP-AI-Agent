"""
Router — every routing decision of the v2 graph lives in THIS file.

Rules: routing functions are PURE — they read GraphState and return a node
name; no LLM calls, no tools, no mutation. GraphState is synced from the
engine at the end of every node (runtime.sync_updates), so the entry router
sees exactly what the legacy route() saw live on the engine.

Node names keep the legacy spelling ("address_validation",
"ticket_registration") for trace/test parity; renaming is a deliberate later
commit, not a side effect of the migration.

R3 scope: the walker guard chain (docs/ROADMAP_REFACTORING.md §5) migrates
here group by group as conditional-edge functions for the diagnosis subgraph.
"""

from __future__ import annotations

from .state import GraphState

# Node names — the single place they are spelled out.
ADDRESS_VALIDATION = "address_validation"
DIAGNOSIS = "diagnosis"
SIDE_TOPIC = "side_topic"
TICKET_REGISTRATION = "ticket_registration"
CLOSING = "closing"

ENTRY_TARGETS = (ADDRESS_VALIDATION, DIAGNOSIS, TICKET_REGISTRATION, CLOSING)


def route_entry(state: GraphState) -> str:
    """Deterministic entry routing (ports agent/graph.py route() unchanged).

    Priority: case_closed wins (END stage); a mid-ticket-dialogue turn goes to
    the dedicated node so diagnosis narration cannot compete with the contact
    questions; then identified -> diagnosis, else keep identifying.
    """
    if state.case_closed:
        return CLOSING
    if state.ticket_stage:
        return TICKET_REGISTRATION
    return DIAGNOSIS if state.customer_id else ADDRESS_VALIDATION
