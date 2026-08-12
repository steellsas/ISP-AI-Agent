"""
Diagnosis stage.

R2 thin wrapper (make_diagnosis_node): ports diagnosis() from agent/graph.py
verbatim — the 9-step engine pipeline runs inside one node for now:
ensure_diagnosed -> ingest evidence -> side-topic freeze -> inform-close ->
solver drive -> walker -> shadow solve -> deterministic action -> narration.

R3 target: this pipeline becomes an explicit subgraph over the sibling files
(diagnose.py, solver_gate.py, evidence_drive.py, walker.py, executor.py,
narrator.py) with the walker guard chain (roadmap §5) as conditional edges.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from ...router import DIAGNOSIS, SIDE_TOPIC
from ...runtime import DIAGNOSIS_NODE_PROMPT, SIDE_TOPIC_PROMPT, narrate, sync_updates
from ...state import GraphState


def make_diagnosis_node(engine: Any):
    def diagnosis_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        # Deterministic driver: diagnose ONCE on entering the stage, so the
        # verdict + resolution strategy no longer depend on the model.
        engine.ensure_diagnosed()
        # Ledger v1: the caller's utterance lands on the evidence ledger BEFORE
        # anyone acts on it.
        engine._ingest_client_evidence(user_input)
        # A deviation FREEZES the engine for the turn — no walker/solver/action
        # on side chatter; the LLM answers from FAQ facts and returns to the anchor.
        if engine.classify_side_topic(user_input):
            reply = narrate(engine, user_input, frozenset(), SIDE_TOPIC_PROMPT, SIDE_TOPIC)
            return sync_updates(engine, user_input=user_input, reply=reply)
        # Deterministic close for INFORM mode (outage / billing / no-strategy).
        engine._maybe_close_inform(user_input)
        # Piloted direction (SOLVER_DRIVE): the solver owns the whole turn.
        driven = engine.solver_drive_turn(user_input)
        if driven is not None:
            engine._active_node = DIAGNOSIS
            engine.tracer.emit(
                "node", node="diagnosis_solver", customer_id=engine.state.customer_id
            )
            get_stream_writer()(driven)
            return sync_updates(engine, user_input=user_input, reply=driven)
        engine._advance_resolution(user_input)
        engine._shadow_solve(user_input)
        # An ACTION step reached by the caller's reply runs deterministically
        # BEFORE the LLM narrates — the model only phrases the verified result.
        engine.ensure_action_done()
        reply = narrate(engine, user_input, None, DIAGNOSIS_NODE_PROMPT, DIAGNOSIS)
        engine._mark_step_presented()
        return sync_updates(engine, user_input=user_input, reply=reply)

    return diagnosis_node
