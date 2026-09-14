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
from ...runtime import node_update
from ...state import GraphState


def diagnose_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)
    return node_update(state, _diagnose(state, rt, state.turn.user_input))


def _diagnose(state: Any, rt: Any, user_input: str | None) -> None:
    from ....identification_flow import prefill_slots_from_text
    from ....perception_flow import classify_side_topic, ingest_client_evidence, pre_turn_guards
    from ....walker_flow import ensure_diagnosed

    ensure_diagnosed(state, rt)
    # One-owner principle (live A-2, 2026-09-07): the deterministic turn
    # head (prefill + pre_turn_guards) runs BEFORE the solver/walker —
    # solver_gate used to answer before narrate()'s guards could read a
    # safety-question answer, and "Taip taip dėl KITO adreso" leaked into
    # the walker's question. The latch prevents a double run when the
    # narrator later finishes the same turn via narrate().
    if user_input:
        # user_turn trace stays with narrate()/the solver commit — no duplicates.
        prefill_slots_from_text(state, rt, user_input)
        pre_turn_guards(state, rt, user_input)
        state.turn.pre_turn_head_done = True
    ingest_client_evidence(state, rt, user_input)
    # A corroborated deviation freezes the engine this turn (read by the router).
    state.turn.side_topic_active = bool(classify_side_topic(state, rt, user_input))
