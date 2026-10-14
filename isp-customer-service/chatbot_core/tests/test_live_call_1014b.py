"""Live call 2026-10-14 (b): the router is dead, the offer was never spoken, and the caller
with no computer was told to plug the cable into one."""

import pytest

from tests.test_case_rule import BASE
from tests.test_step_refusal import _hear, _Tracer


@pytest.fixture
def dead_router(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    assert case_rule.plan(state, rt).rule == "case.check_lights"
    state.case.step_said = state.case.step
    _hear(state, "Nedega nė viena")
    record_client(state, rt, "lights", "off")
    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.check_power"
    state.case.step_said = state.case.step
    return state, rt, tracer


def test_an_answer_with_palaukite_is_an_answer(dead_router):
    """„Tuoje palaukite, tvirtai įkištas" — the offer is said, not swallowed by the wait."""
    from agent.decide.rules import case_rule
    from agent.ledger import record_client
    from agent.perceive.detectors import INTENT_ANSWER, INTENT_IN_PROGRESS
    from agent.perceive.node import _answer_beats_wait

    state, rt, _ = dead_router
    _hear(state, "Tuoje palaukite, tvirtai įkištas.")
    state.dialog.last_intent = INTENT_IN_PROGRESS
    awaited = state.case.awaiting
    record_client(state, rt, "power_cable", "plugged")
    _answer_beats_wait(state, rt, awaited, False)
    assert state.dialog.last_intent == INTENT_ANSWER

    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.offer_bridge"
    assert "perduosime meistrui" in plan.say.text and "kompiuter" in plan.say.text


def test_a_new_step_is_never_swallowed_by_the_wait(dead_router):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client
    from agent.perceive.detectors import INTENT_IN_PROGRESS
    from agent.speak.context_card import _case_step

    state, rt, _ = dead_router
    record_client(state, rt, "power_cable", "plugged")
    plan = case_rule.plan(state, rt)
    state.turn.plan = plan.model_dump() if hasattr(plan, "model_dump") else plan.__dict__
    state.dialog.last_intent = INTENT_IN_PROGRESS
    state.dialog.awaiting = "power_cable"
    lines = _case_step(state, rt)
    assert not any("THE STEP WAITS" in line for line in lines)


@pytest.mark.parametrize("said", ["Mhm.", "Aha", "mhm"])
def test_a_backchannel_is_not_consent(said):
    from agent.perceive.detectors import detect_bridge_consent

    assert detect_bridge_consent(said) is None


def test_no_computer_mid_step_skips_the_bridge(dead_router):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client

    state, rt, tracer = dead_router
    record_client(state, rt, "power_cable", "plugged")
    case_rule.plan(state, rt)  # the offer
    state.case.step_said = state.case.step
    record_client(state, rt, "bridge_agreed", "yes")
    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.connect_direct"
    state.case.step_said = state.case.step
    _hear(state, "Aš neturiu kompiuterio, tik telefoną naudoju.")
    record_client(state, rt, "has_computer", "no")
    plan = case_rule.plan(state, rt)

    assert plan.rule != "case.connect_direct" and plan.rule != "case.confirm"
    assert "no_longer_applies" in tracer.moves()
    assert "connect_direct" not in state.case.worked  # the summary must not say it was done


def test_a_no_is_never_a_done_report():
    from agent.perceive.detectors import detect_yes_no
    from agent.resolution import Outcome

    assert detect_yes_no("Ne, ne įkišau, nes neturiu kompiuterį.") is Outcome.NO


def test_tetas_is_family():
    from agent.perceive.caller import detect_caller_relation

    assert detect_caller_relation("Taip, Gedras vardu, tėtas mano.") == "family"
