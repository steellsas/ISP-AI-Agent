"""
Router — every routing decision of the v2 graph lives in THIS file.

Rules: routing functions are PURE — they read GraphState and return a node
name; no LLM calls, no tools, no mutation. Every node returns the full state
(runtime.run_on_state), so the routers read exactly what the last node left.

Node names keep the legacy spelling ("address_validation",
"ticket_registration") for trace/test parity; renaming is a deliberate later
commit, not a side effect of the migration.

R3 scope: the walker guard chain (docs/ROADMAP_REFACTORING.md §5) migrates
here group by group as conditional-edge functions for the diagnosis subgraph.
"""

from __future__ import annotations

from .state import GraphState

# Node names — the single place they are spelled out.
PERCEIVE = "perceive"
DECIDE = "decide"
ADDRESS_VALIDATION = "address_validation"
DIAGNOSIS = "diagnosis"
SIDE_TOPIC = "side_topic"
TICKET_REGISTRATION = "ticket_registration"
CLOSING = "closing"

ENTRY_TARGETS = (ADDRESS_VALIDATION, DIAGNOSIS, TICKET_REGISTRATION)


def route_after_decide(state: GraphState) -> str:
    """A turn the policy chain planned is done; otherwise a stage node takes it."""
    return "end" if state.turn.plan is not None else route_entry(state)


def route_entry(state: GraphState) -> str:
    """Deterministic entry routing for the turns no policy rule owned.

    A mid-ticket-dialogue turn goes to the dedicated node so diagnosis narration
    cannot compete with the contact questions; then identified -> diagnosis, else
    keep identifying. (A closed case is always planned by the closing rules.)
    """
    if state.ticket.stage:
        return TICKET_REGISTRATION
    return DIAGNOSIS if state.identity.customer_id else ADDRESS_VALIDATION


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
    action runs on side chatter. The perceive node sets the signal before the
    turn head's guards run, so a mechanic those guards opened this turn (the
    ticket dialogue, the end-confirm, a resume hold) still owns the turn."""
    if not state.turn.side_topic_active:
        return DIAG_SOLVER_GATE
    engaged = (
        state.ticket.stage
        or state.closing.case_closed
        or not state.identity.customer_id
        or state.diagnosis.evidence_conflict
        or state.dialog.end_confirm_pending
        or state.dialog.resume_hold_due
    )
    return DIAG_SOLVER_GATE if engaged else DIAG_SIDE_TOPIC


def route_after_solver_gate(state: GraphState) -> str:
    """A non-None turn.reply means the solver owned the whole turn (SOLVER_DRIVE)
    — the walker and the LLM narrator are skipped, exactly like the legacy
    in-node early return."""
    return "end" if state.turn.reply is not None else DIAG_WALKER
