"""Live calls 2026-10-14 (Andrius): what the engine waits for is what is asked, garbage is
not an answer, the conclusion is honest, and a demand is not lost behind a side question."""

from tests.test_case_rule import BASE
from tests.test_step_refusal import _hear, _Tracer, at_the_lights  # noqa: F401


def test_garbled_speech_is_not_a_no():
    from agent.evidence import polarity, read_pending_answer

    assert read_pending_answer("lights", "Gekine matone") is None
    assert polarity("Gekine matone") is None
    assert read_pending_answer("lights", "Ne, nedega") == "off"
    assert read_pending_answer("lights", "ne dega") == "off"


def test_without_a_goal_the_open_question_is_the_engines(at_the_lights):
    from agent.speak.context_card import _next_step_words, _open_question

    state, _rt, _ = at_the_lights
    lines = _open_question(state, [])
    assert len(lines) == 1 and "OPEN QUESTION" in lines[0]
    assert _next_step_words(state) in lines[0]
    assert _open_question(state, ["PLAN GOAL — something"]) == []


def test_the_conclusion_does_not_claim_an_untried_fix(make_state, make_runtime):
    from agent.contract import cards as catalog
    from agent.decide.rules.case_rule import _technician_why
    from agent.ledger import record_client, record_telemetry

    state, rt = make_state("+37060020112"), make_runtime(tracer=_Tracer())
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "traffic": "none"})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 0
    card = catalog.card("router_hung")

    untried = _technician_why(state, card)
    assert "nepavyko" in untried and "perkrau" not in untried.lower()
    state.case.spent.append("router_hung")
    assert _technician_why(state, card) == _technician_why.__globals__["maybe_phrase"](
        card.escalate.need
    )


def test_a_demand_with_a_question_goes_to_the_case(at_the_lights):
    from agent.decide.rules.stage import _demands_a_ticket

    state, _rt, _ = at_the_lights
    _hear(state, "Kur tas routeris? Registruokite gedimą")
    assert _demands_a_ticket(state) is True
    _hear(state, "Kur tas routeris?")
    assert _demands_a_ticket(state) is False
