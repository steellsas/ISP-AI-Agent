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

from ...state import GraphState


def make_diagnose_node(engine: Any):
    def diagnose_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        engine.ensure_diagnosed()
        # Vieno savininko principas (A-2 gyva 2026-09-07): deterministinė turn'o
        # galva (prefill + pre_turn_guards) vykdoma PRIEŠ solverį/walker'į —
        # solver_gate atsakydavo anksčiau, nei narrate() sluoksnio guards
        # perskaitydavo saugiklio klausimo atsakymą, ir „Taip taip dėl KITO
        # adreso" nutekėdavo į walker'io klausimą. Latch'as saugo nuo dvigubo
        # vykdymo, kai vėliau tą patį turn'ą narratorius užbaigia narrate().
        if user_input:
            # user_turn trace lieka narrate()/solver commit'ui — be dublikatų.
            engine._prefill_slots_from_text(user_input)
            engine._pre_turn_guards(user_input)
            engine._pre_turn_head_done = True
        engine._ingest_client_evidence(user_input)
        side = bool(engine.classify_side_topic(user_input))
        return {"turn": state.turn.model_copy(update={"side_topic_active": side})}

    return diagnose_node
