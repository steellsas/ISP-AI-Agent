"""Confirm, do not guess (Andrius, 2026-10-12).

*„Kaip klientas atsakytų, agentas turi suprasti, teigiamai ar neigiamai atsakė į klausimą; galima
visuomet paduoti pasitikrinimo klausimą… patikslinti visuomet geriau nei galvoti ar spėti, ką
klientas pasakė."*

A reading only the model made — no word of the caller's backs it — is parked and confirmed:
„Noriu įsitikinti, kad gerai supratau: … — ar teisingai?". Eval S4 (2026-10-12) is the case:
„Vis tiek nedega" to the power question became „the lead was out", and „Neturiu kito routerio,
tik kompiuterį" became „I plugged it in".
"""

import pytest
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry

from tests.diagnosis.test_case_rule import said
from tests.diagnosis.test_facts import BASE

FUNCTION = "Patikslinti, ne spėti"


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    return state, rt


def _at(call, module):
    """The dead router, the caller at it, the lights out — standing on `module`."""
    state, rt = call
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    record_client(state, rt, "has_computer", "yes")
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    case_rule.plan(state, rt)  # lights
    said(state, rt, "lights", "off")
    plan = case_rule.plan(state, rt)  # check_power
    if module == "plug_power":
        said(state, rt, "power_cable", "unplugged")
        plan = case_rule.plan(state, rt)
    assert plan.rule == f"case.{module}"
    state.case.step_said = state.case.step
    return state, rt


def _hear(state, words, model=None):
    state.dialog.turn_count += 1
    state.dialog.last_heard = words
    state.turn.perception = {"step": model} if model else None


class TestThePowerAnswer:
    def test_a_guess_is_confirmed(self, call):
        state, rt = _at(call, "check_power")
        _hear(state, "Vis tiek nedega", {"label": "no", "is_answer": True, "confidence": 1.0})
        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.confirm"
        assert "maitinimo laidas buvo ištrauktas — ar teisingai?" in plan.say.text
        assert "power_cable" not in (state.case.said or [])

    def test_confirmed_the_lead_is_plugged_in(self, call):
        state, rt = _at(call, "check_power")
        _hear(state, "Vis tiek nedega", {"label": "no", "is_answer": True, "confidence": 1.0})
        case_rule.plan(state, rt)
        _hear(state, "Taip, buvo ištrauktas")

        assert case_rule.plan(state, rt).rule == "case.plug_power"
        assert state.case.facts["power_cable"] == "unplugged"

    def test_denied_the_question_is_asked_simply(self, call):
        state, rt = _at(call, "check_power")
        _hear(state, "Vis tiek nedega", {"label": "no", "is_answer": True, "confidence": 1.0})
        case_rule.plan(state, rt)
        _hear(state, "Ne, ne")
        case_rule.plan(state, rt)

        assert "power_cable" not in (state.case.said or [])
        assert state.case.unclear == state.case.step  # „Tai įkištas ar ištrauktas?"

    def test_the_callers_own_words_need_no_confirmation(self, call):
        state, rt = _at(call, "check_power")
        _hear(state, "Įkištas, tvirtai įkištas")
        state.case.facts.pop("power_cable", None)
        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.confirm"


class TestThePlugDone:
    def test_a_done_only_the_model_heard_is_confirmed(self, call):
        state, rt = _at(call, "plug_power")
        _hear(
            state,
            "Neturiu kito routerio, tik kompiuterį",
            {"label": "done", "is_answer": True, "confidence": 1.0},
        )
        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.confirm"
        assert "Ar jau įkišote maitinimo laidą" in plan.say.text

    def test_no_it_stays_on_the_instruction(self, call):
        state, rt = _at(call, "plug_power")
        at = state.case.step
        _hear(state, "Hmm", {"label": "done", "is_answer": True, "confidence": 1.0})
        case_rule.plan(state, rt)
        _hear(state, "Ne, dar ne")
        case_rule.plan(state, rt)

        assert state.case.step == at and state.case.confirming is None

    def test_yes_goes_on_to_the_line_read(self, call):
        state, rt = _at(call, "plug_power")
        _hear(state, "Hmm", {"label": "done", "is_answer": True, "confidence": 1.0})
        case_rule.plan(state, rt)
        _hear(state, "Taip")
        case_rule.plan(state, rt)

        assert case_rule._current(state).module == "verify"

    def test_their_own_words_need_no_confirmation(self, call):
        state, rt = _at(call, "plug_power")
        _hear(state, "Įkišau, lemputės jau dega")
        plan = case_rule.plan(state, rt)

        assert plan.rule != "case.confirm"
        assert case_rule._current(state).module == "verify"


def test_on_the_way_is_not_a_yes(make_state, make_runtime):
    """„Palaukite, einu prie routerio" — live 2026-10-12 the agent said „palauksiu" and gave the
    lights step in the same breath."""
    from agent.perceive.detectors import INTENT_IN_PROGRESS

    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    assert case_rule.plan(state, rt).rule == "case.reach"
    state.case.step_said = state.case.step
    _hear(
        state,
        "Palaukite, einu prie routerio",
        {"label": "yes", "is_answer": True, "confidence": 1.0},
    )
    state.dialog.last_intent = INTENT_IN_PROGRESS
    plan = case_rule.plan(state, rt)

    assert "reachable" not in (state.case.said or [])
    assert plan.rule not in ("case.check_lights", "case.confirm")

    from agent.speak.context_card import context_card

    state.turn.plan = plan.model_dump() if hasattr(plan, "model_dump") else plan.__dict__
    state.dialog.awaiting = "reachable"
    card = context_card(state, rt)
    assert "say you will wait" in card and "THE STEP WAITS" in card
    assert "SAY THIS STEP" not in card


def test_the_answer_after_a_scripted_question_is_read(call):
    """The confirm question is a scripted phrase — no LLM, so `turn_count` does not move. The
    caller's next message must still be read as the answer (eval S4, 2026-10-12: the agent
    asked „Ar jūs jau prie routerio?" ten times)."""
    state, rt = _at(call, "check_power")
    _hear(state, "Vis tiek nedega", {"label": "no", "is_answer": True, "confidence": 1.0})
    state.messages.append({"role": "user", "content": "Vis tiek nedega"})
    case_rule.plan(state, rt)
    state.dialog.last_heard = "Taip"  # no turn_count += 1: nothing spoke through the LLM
    state.turn.perception = None
    state.messages.append({"role": "user", "content": "Taip"})

    assert case_rule.plan(state, rt).rule == "case.plug_power"


@pytest.mark.parametrize(
    ("said", "label"),
    [
        ("Laidas įkištas, tvirtai", "yes"),
        ("Taip, įkištas", "yes"),
        ("Ne, neįkištas", "no"),  # the negation first: „neįkištas" holds „įkištas"
        ("Oi, maitinimo laidas ištrauktas iš rozetės", "no"),
        ("Laidas buvo iškritęs", "no"),
        ("Vis tiek nedega", None),  # about the lights, not the lead — this one is confirmed
    ],
)
def test_the_power_answer_in_the_callers_words(said, label):
    from agent.perceive.detectors import detect_power_cable

    assert detect_power_cable(said) == label


@pytest.mark.parametrize(
    ("said", "label"),
    [
        ("Taip, jau stoviu prie routerio", "yes"),
        ("Jau esu prie jo", "yes"),
        ("Palaukite, einu prie routerio", None),  # on the way — not an answer yet
        ("Tuoj nueisiu", None),
        ("Galėtume kartu patikrinti", None),  # this one is confirmed
        ("Ne, negaliu", "no"),
    ],
)
def test_the_reach_answer_in_the_callers_words(said, label):
    from agent.perceive.detectors import detect_reach

    assert detect_reach(said) == label
