"""A step the caller declines (Andrius, 2026-10-14).

„Su pirmu atsisakymu neturi nutraukti pokalbio — turime paaiškinti." The first refusal gets the
reason it matters and the same step once more. The second: a question is left out and the fix
goes on with what is still possible („nenori pasakyti apie lemputes, bet gali patikrinti
maitinimą"); an action the rest stands on ends in the conclusion — what we did, what they could
not / did not want to do — and a registration. Not a refusal: done without a result, still
doing it, not following, not at home.
"""

import pytest

from tests.diagnosis.test_facts import BASE

FUNCTION = "Atsisakytas žingsnis"


class _Tracer:
    session_id = "R"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def moves(self):
        return [e.get("move") for e in self.events if e["type"] == "case"]


def _hear(state, words):
    state.dialog.turn_count += 1
    state.dialog.last_heard = words
    state.turn.perception = None


@pytest.fixture
def at_the_lights(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    plan = case_rule.plan(state, rt)
    assert plan.rule == "case.check_lights"
    state.case.step_said = state.case.step
    return state, rt, tracer


@pytest.mark.parametrize(
    ("said", "how"),
    [
        ("Nenoriu tikrinti lempučių", "wont"),
        ("Negaliu, nepasiekiu routerio", "cant"),
        ("Nesu namuose", None),  # cannot NOW — the later/callback path
        ("Perkroviau, bet nieko nepasikeitė", None),  # done, no result
        ("Nesuprantu, ką daryti", None),  # not following — explain differently
        ("Tuoj, einu", None),  # still doing it
    ],
)
def test_a_refusal_is_told_apart(said, how):
    from agent.perceive.detectors import detect_step_refusal

    assert detect_step_refusal(said) == how


def test_the_first_refusal_is_explained_not_ended(at_the_lights):
    from agent.decide.rules import case_rule

    state, rt, tracer = at_the_lights
    _hear(state, "Nenoriu tikrinti lempučių")
    plan = case_rule.plan(state, rt)

    assert plan.rule == "case.refusal_explained"
    assert "why this step matters" in plan.say.goal and "technician" in plan.say.goal
    assert state.ticket.stage is None


def test_a_question_declined_twice_is_left_out_and_the_fix_goes_on(at_the_lights):
    from agent.decide.rules import case_rule

    state, rt, tracer = at_the_lights
    _hear(state, "Nenoriu tikrinti lempučių")
    case_rule.plan(state, rt)
    state.case.step_said = state.case.step
    _hear(state, "Ne, nesakysiu")
    plan = case_rule.plan(state, rt)

    assert "step_declined" in tracer.moves()
    assert plan.rule == "case.check_power"  # „…bet gali patikrinti maitinimą"
    assert state.ticket.stage is None


def test_the_conclusion_says_what_was_left_out(at_the_lights):
    from agent.contract import cards as catalog
    from agent.decide.rules import case_rule
    from agent.decide.rules.case_rule import _summary_words
    from agent.ledger import facts_of

    state, rt, _ = at_the_lights
    _hear(state, "Nenoriu tikrinti lempučių")
    case_rule.plan(state, rt)
    state.case.step_said = state.case.step
    _hear(state, "Ne, nesakysiu")
    case_rule.plan(state, rt)
    state.case.worked.append("check_power")

    told = _summary_words(state, catalog.card(state.case.fault), facts_of(state))
    assert "nepatikrinta: routerio lemputės (nenorėjote)" in told["nepavyko"]


def test_an_action_declined_twice_ends_in_the_conclusion(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "traffic": "none"})
    record_client(state, rt, "fail_scope", "all")
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 0
    plan = case_rule.plan(state, rt)
    while plan.rule != "case.reboot":
        state.case.step += 1
        plan = case_rule.plan(state, rt)
    state.case.step_said = state.case.step
    _hear(state, "Nedarysiu to")
    assert case_rule.plan(state, rt).rule == "case.refusal_explained"
    state.case.step_said = state.case.step
    _hear(state, "Ne, nedarysiu")
    case_rule.plan(state, rt)  # the conclusion
    case_rule.plan(state, rt)  # the registration

    assert state.ticket.reason == "klientas_nenori"
    assert "nepatikrinta: routerio perkrovimas (nenorėjote)" in (state.case.summary or {}).get(
        "nepavyko", ""
    )


def test_a_refusal_is_not_an_answer(at_the_lights):
    """„Ne, nesakysiu" — the bare „ne" read as „not lit" must not survive (eval S4e: the ticket
    said „routerio lemputės: nedega" for a caller who would not look)."""
    from agent.decide.rules import case_rule
    from agent.ledger import record_client

    state, rt, _ = at_the_lights
    record_client(state, rt, "lights", "off")  # what a reader made of the „Ne"
    _hear(state, "Ne, nesakysiu")
    case_rule.plan(state, rt)

    assert "lights" not in state.case.facts and "lights" not in state.case.said
