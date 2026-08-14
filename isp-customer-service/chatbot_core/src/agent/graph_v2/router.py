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


# --- Diagnosis subgraph (R3): node names + routing -------------------------

DIAG_DIAGNOSE = "diag_diagnose"
DIAG_SIDE_TOPIC = "diag_side_topic"
DIAG_SOLVER_GATE = "diag_solver_gate"
DIAG_WALKER = "diag_walker"
DIAG_EXECUTOR = "diag_executor"
DIAG_NARRATOR = "diag_narrator"


def route_after_diagnose(state: GraphState) -> str:
    """A corroborated deviation FREEZES the engine for the turn: the side-topic
    node answers from FAQ facts and returns to the anchor — no walker/solver/
    action runs on side chatter. The flag is set by the diagnose node (the
    classification call mutates engine counters, so it cannot live here)."""
    return DIAG_SIDE_TOPIC if state.turn.side_topic_active else DIAG_SOLVER_GATE


def route_after_solver_gate(state: GraphState) -> str:
    """A non-None turn.reply means the solver owned the whole turn (SOLVER_DRIVE)
    — the walker and the LLM narrator are skipped, exactly like the legacy
    in-node early return."""
    return "end" if state.turn.reply is not None else DIAG_WALKER
