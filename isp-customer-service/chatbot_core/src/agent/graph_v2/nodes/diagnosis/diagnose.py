"""
Diagnose node — telemetry read + evidence ingest + deviation classification.

Order ports the legacy diagnosis() pipeline head verbatim:
1. ensure_diagnosed — diagnose ONCE on entering the stage, so the verdict +
   resolution strategy no longer depend on the model.
2. _ingest_client_evidence — the caller's utterance lands on the evidence
   ledger BEFORE anyone acts on it.
3. classify_side_topic — runs HERE (it mutates engine counters and traces, so
   the routing function must stay pure); the result goes into
   turn.side_topic_active for router.route_after_diagnose.

R3 follow-up: evidence ingest moves to the perception node once perception
merges into one LLM call (roadmap R4). The verdict tree stays pure in
agent/verdict.py.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ....runtime import AgentRuntime
from ...runtime import run_on_state
from ...state import GraphState


def diagnose_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    engine = runtime.context.engine
    return run_on_state(engine, state, lambda: _diagnose(engine, state.turn.user_input))


def _diagnose(engine: Any, user_input: str | None) -> None:
    engine.ensure_diagnosed()
    # One-owner principle (live A-2, 2026-09-07): the deterministic turn
    # head (prefill + pre_turn_guards) runs BEFORE the solver/walker —
    # solver_gate used to answer before narrate()'s guards could read a
    # safety-question answer, and "Taip taip dėl KITO adreso" leaked into
    # the walker's question. The latch prevents a double run when the
    # narrator later finishes the same turn via narrate().
    if user_input:
        # user_turn trace stays with narrate()/the solver commit — no duplicates.
        engine._prefill_slots_from_text(user_input)
        engine._pre_turn_guards(user_input)
        engine.state.turn.pre_turn_head_done = True
    engine._ingest_client_evidence(user_input)
    # A corroborated deviation freezes the engine this turn (read by the router).
    engine.state.turn.side_topic_active = bool(engine.classify_side_topic(user_input))
