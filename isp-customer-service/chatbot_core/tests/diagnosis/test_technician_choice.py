"""Meistras ar kartu? (#79 — live 2026-11-20, a dead router): „atvažiuokite" in the opening
line offered the technician on the first unclear answer; „Taip, galvojau." to „meistrą ar
pabandome kartu?" registered; „Galiu prieiti, pabandome kartu" could not undo it; and the caller
heard „telefonu neišspręsime" before a single check.
"""

import pytest

from tests.understanding.test_analyst_observes import _signal, _Tracer

FUNCTION = "Meistras ar kartu"


@pytest.mark.parametrize(
    ("said", "choice"),
    [
        ("Taip, galvojau.", None),
        ("Taip.", None),
        ("Registruokite meistrą", "technician"),
        ("Geriau tegul atvažiuoja meistras", "technician"),
        ("Pabandome kartu", "try"),
        (
            "Taip, galvojau. Galiu ateiti prie routerio. Pabandome kartu, galiu atėti prie routerą.",
            "try",
        ),
        ("Aš prie routerio, kamandą darom", "try"),
        ("Nereikia meistro, pabandom", "try"),
        ("Pabandėm, bet geriau registruokite meistrą", "technician"),
    ],
)
def test_the_choice_is_read(said, choice):
    from agent.decide.rules.case_rule import technician_choice

    assert technician_choice(said) == choice


@pytest.fixture
def dead_router(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_telemetry

    from tests.diagnosis.test_facts import BASE

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    case_rule.plan(state, rt)  # „Ar galite prieiti?"
    state.case.step_said = state.case.step
    return state, rt, tracer


def _turn(state, rt, text):
    from agent.decide.rules import case_rule

    state.dialog.turn_count += 1
    state.dialog.last_heard = text
    return case_rule.plan(state, rt)


def test_a_wish_from_the_opening_waits_for_a_done_step(dead_router):
    from agent.analyst.node import _wants_technician

    state, rt, _ = dead_router
    _wants_technician(state, rt, _signal("wants_technician", quote="atvažiuokite"))
    assert state.case.technician_offer is None  # nothing checked yet — the fix comes first
    state.case.did.append("reach")
    _wants_technician(state, rt, _signal("wants_technician", quote="atvažiuokite"))
    assert state.case.technician_offer == "due"


def _offered(state, rt):
    state.case.did.append("reach")
    state.case.technician_offer = "due"
    plan = _turn(state, rt, "Hmm")
    assert plan.rule == "case.technician_offer"


def test_a_bare_yes_is_asked_again(dead_router):
    state, rt, _ = dead_router
    _offered(state, rt)
    plan = _turn(state, rt, "Taip, galvojau.")
    assert plan.rule == "case.technician_offer" and "registruoti meistrą" in plan.say.text
    assert state.ticket.stage is None and not state.case.summarised


def test_together_goes_on_with_the_fix(dead_router):
    state, rt, tracer = dead_router
    _offered(state, rt)
    _turn(state, rt, "Galiu ateiti prie routerio. Pabandome kartu.")
    assert "technician_not_wanted" in tracer.moves()
    assert state.ticket.stage is None and not state.case.summarised


def test_the_technician_before_the_checks_gets_one_offer_to_try(dead_router):
    """The card's must-do (lights, power) comes first — once; a „ne" registers."""
    state, rt, tracer = dead_router
    _offered(state, rt)
    plan = _turn(state, rt, "Registruokite meistrą")
    assert plan.rule == "case.phone_work_offer"
    assert state.ticket.stage is None


def test_back_to_the_fix_from_the_contact_questions(make_state, make_runtime):
    """Call 0008: „Aš prie routerio, darom" while the number was asked."""
    from agent.decide.rules.ticket import ticket_capture
    from agent.graph_v2.state import TicketContext

    state, rt = make_state("+37060020112"), make_runtime()
    state.case.fault, state.case.solution = "no_mac_observed", 0
    state.case.summarised = True
    state.ticket.stage, state.ticket.reason = "phone", "klientas_praso"
    state.ticket.context = TicketContext(intro_done=True, phone_asked=True)
    ticket_capture(state, rt, "Aš prie routerio, kamandą darom")
    assert state.ticket.stage is None and not state.case.summarised
