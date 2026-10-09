"""Live call 2026-10-09 (dead router, „nesu namuose") — N1..N5, with the caller's own words.

N1 „not at home" at ANY question of the fix: ask WHEN once, then homework + callback with that
time, or a technician when they cannot say. N2 an answer to identification is not an answer to
the Case. N3 the bind waits for the line to show the device. N4 the name with a question in
the sentence; „Nesunamosiu" is not a name. N5 „neturiu TOKIŲ bėdų" is not a fault.
"""

import pytest


class _Tracer:
    session_id = "3d"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def moves(self):
        return [e.get("move") for e in self.events if e["type"] == "case"]


@pytest.fixture
def fixing(make_state, make_runtime):
    """The dead-router fix under way, the caller identified."""
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    state.identity.caller_name = "Andrius"
    state.intake.problem_type = "internet_down"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt, tracer


def _hear(state, text):
    state.dialog.last_heard = text
    state.dialog.turn_count += 1


class TestN1NotAtHome:
    def test_heard_at_any_question_asks_when(self, fixing):
        from agent.decide.rules.case_rule import plan

        state, rt, tracer = fixing
        state.case.awaiting = "lights"  # we were asking about the lights
        _hear(state, "Ne, ne, aš nesu namuose.")
        p = plan(state, rt)

        assert state.case.facts["reachable"] == "no"
        assert p.rule == "case.ask_when" and "Kada galėsite" in p.say.text

    def test_a_time_said_skips_the_question(self, fixing):
        from agent.decide.rules.case_rule import plan

        state, rt, _ = fixing
        _hear(state, "Aš jums perskambinsiu, kai grįšiu po valandos.")
        p = plan(state, rt)

        assert state.case.facts["_available_when"] == "po valandos"
        assert p.rule == "case.homework"

    def test_the_answer_to_when(self, fixing):
        from agent.decide.rules.case_rule import plan

        state, rt, _ = fixing
        _hear(state, "Esu darbe.")
        plan(state, rt)
        _hear(state, "Vakare.")
        p = plan(state, rt)

        assert state.case.facts["_available_when"] == "vakare"
        assert p.rule == "case.homework"

    def test_cannot_say_when_gets_a_technician(self, fixing):
        from agent.decide.rules.case_rule import plan

        state, rt, tracer = fixing
        _hear(state, "Nesu namuose.")
        plan(state, rt)
        _hear(state, "Nežinau, gal negalėsiu.")
        plan(state, rt)

        assert "cannot_say_when" in tracer.moves()

    def test_the_time_goes_on_the_ticket(self, fixing):
        from agent.executor_flow import register_ticket_from_state

        state, _, _ = fixing
        created = []

        def tools(name, args):
            if name == "create_ticket":
                created.append(args)
                return {"success": True, "ticket_id": "T"}
            return {}

        from tests.calls import make_runtime

        rt = make_runtime(fake_tools=tools)
        state.case.facts["_available_when"] = "po valandos"
        register_ticket_from_state(state, rt)
        assert "galės: po valandos" in created[0]["problem_description"]


def test_n2_an_identification_answer_is_not_read_by_the_case(fixing):
    from agent.decide.rules.case_rule import _absorb

    state, rt, _ = fixing
    state.case.step = 0  # „ar galite prieiti?" is out
    state.case.awaiting = "reachable"
    state.turn.ident_answer = True  # „Taip, kitas šeimos nario vardu"
    assert _absorb(state, rt, {"reachable": "yes"}) == "waiting"
    assert state.case.step == 0


class TestN3BindWaitsForTheLine:
    def test_no_device_on_the_line_no_bind(self, fixing):
        from agent.contract.schema import ModuleCall
        from agent.decide.rules.case_rule import _line_does_not_show

        state, rt, tracer = fixing
        state.case.step = 5
        call = ModuleCall(module="bind", args={"device": "computer"})
        first = _line_does_not_show(state, rt, call, {"device_seen": "no"})
        assert first.rule == "case.probe"  # the line is read first, in the same turn
        p = _line_does_not_show(state, rt, call, {"device_seen": "no"})
        assert p is not None and "dar nematau" in p.say.text
        assert p.action.type == "none"  # no update_mac
        assert state.case.step == 4  # back to the step that should have produced it

    def test_a_device_seen_lets_the_bind_run(self, fixing):
        from agent.contract.schema import ModuleCall
        from agent.decide.rules.case_rule import _line_does_not_show

        state, rt, _ = fixing
        call = ModuleCall(module="bind", args={"device": "computer"})
        assert _line_does_not_show(state, rt, call, {"device_seen": "yes"}) is None


class TestN4CallerName:
    def _intro(self, make_state, make_runtime, said):
        from agent.decide.rules.head import caller_intro

        state, rt = make_state("+37060012353"), make_runtime()
        state.identity.customer_id = "CUST009"
        state.identity.result_pending = True
        caller_intro(state, rt, said)
        return state.identity.caller_name

    def test_the_name_with_a_question_in_the_sentence(self, make_state, make_runtime):
        said = "Mano vardas — koks jūsų vardas? Mano vardas — Andrius."
        assert self._intro(make_state, make_runtime, said) == "Andrius"

    def test_not_at_home_is_not_a_name(self, make_state, make_runtime):
        assert self._intro(make_state, make_runtime, "Nesunamosiu.") is None


@pytest.mark.parametrize(
    ("said", "problem"),
    [
        ("Neturiu tokių bėdų, o kodėl jūs sakote, kad aš turiu interneto bėdų?", None),
        ("Neturiu jokių problemų", None),
        ("Neveikia internetas", "internet_down"),
    ],
)
def test_n5_a_denied_fault_is_not_a_fault(said, problem):
    from agent.perceive.nlu import classify_problem

    assert classify_problem(said) == problem


@pytest.mark.parametrize(
    ("said", "agreed"),
    [
        ("Gerai, tinka, paskambinsiu", "yes"),  # eval S4c: got the homework again
        ("Taip", "yes"),
        ("Ačiū, viso gero", "yes"),  # a goodbye here is the consent
        ("Ne, geriau užregistruokite meistrą", "no"),
        ("Netinka", None),  # not „tinka" — whole words only
    ],
)
def test_n1_the_homework_answer_is_read(fixing, said, agreed):
    from agent.decide.rules.case_rule import _read_homework_answer

    state, rt, _ = fixing
    state.case.awaiting = "later_agreed"
    state.dialog.last_heard = said
    assert _read_homework_answer(state, rt) == agreed
