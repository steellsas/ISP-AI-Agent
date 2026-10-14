"""v3 D — the analyst observes, the engine decides (Andrius, 2026-10-13).

The analyst (a background LLM read of the whole call) may now report two more observations:
`dead_end` (the fix is going round in circles) and `wants_technician` (the caller would rather
have a technician). Neither decides anything: the engine's own ladder and questions do.
"""

import pytest

from tests.test_case_rule import BASE


class _Tracer:
    session_id = "D"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})

    def moves(self):
        return [e.get("move") for e in self.events if e["type"] == "case"]


@pytest.fixture
def fixing(make_state, make_runtime):
    from agent.decide.rules import case_rule
    from agent.ledger import record_client, record_telemetry

    tracer = _Tracer()
    state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST112"
    record_telemetry(state, rt, {**BASE, "device_seen": False})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 0
    case_rule.plan(state, rt)  # the lights question
    state.case.step_said = state.case.step
    return state, rt, tracer


def _signal(kind, **fields):
    from agent.analyst.signals import Signal

    return Signal(type=kind, confidence=0.9, turn_index=99, **fields)


def test_the_new_signals_parse():
    from agent.analyst.signals import parse

    raw = (
        '{"signals": [{"type": "dead_end", "value": "neranda routerio", "confidence": 0.8},'
        ' {"type": "wants_technician", "quote": "gal geriau atvažiuotų", "confidence": 0.8}]}'
    )
    assert [s.type for s in parse(raw, turn_index=3)] == ["dead_end", "wants_technician"]


class TestDeadEnd:
    def test_the_step_is_treated_as_stuck(self, fixing):
        from agent.analyst.node import _dead_end
        from agent.decide.rules.case_rule import _no_way_forward

        state, rt, _ = fixing
        assert not _no_way_forward(state)
        _dead_end(state, rt, _signal("dead_end", value="neranda routerio"))
        assert _no_way_forward(state)

    def test_the_engine_gives_one_more_chance_first(self, fixing):
        from agent.analyst.node import _dead_end
        from agent.decide.rules import case_rule

        state, rt, tracer = fixing
        _dead_end(state, rt, _signal("dead_end"))
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Nežinau, nerandu"
        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.last_chance"  # the engine's own ladder, not a ticket yet
        assert state.ticket.stage is None

    def test_another_step_is_not_stuck(self, fixing):
        from agent.analyst.node import _dead_end
        from agent.decide.rules.case_rule import _no_way_forward

        state, rt, _ = fixing
        _dead_end(state, rt, _signal("dead_end"))
        state.case.step += 1
        assert not _no_way_forward(state)


class TestWantsTechnician:
    def test_an_inference_is_asked_first(self, fixing):
        from agent.analyst.node import _wants_technician
        from agent.decide.rules import case_rule

        state, rt, _ = fixing
        _wants_technician(state, rt, _signal("wants_technician", quote="gal geriau atvažiuotų"))
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Hmm"
        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.technician_offer"
        assert "Ar norite, kad užregistruočiau meistrą" in plan.say.text
        assert state.ticket.stage is None  # nothing registered on an inference

    def test_yes_registers_for_the_callers_reason(self, fixing):
        from agent.analyst.node import _wants_technician
        from agent.decide.rules import case_rule

        state, rt, _ = fixing
        _wants_technician(state, rt, _signal("wants_technician"))
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Taip, geriau meistrą"
        case_rule.plan(state, rt)  # the conclusion turn
        case_rule.plan(state, rt)

        assert state.ticket.reason == "klientas_praso"

    def test_no_goes_on_with_the_fix(self, fixing):
        from agent.analyst.node import _wants_technician
        from agent.decide.rules import case_rule

        state, rt, tracer = fixing
        _wants_technician(state, rt, _signal("wants_technician"))
        case_rule.plan(state, rt)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Ne, bandom toliau"
        case_rule.plan(state, rt)

        assert "technician_not_wanted" in tracer.moves()
        assert state.ticket.stage is None and not state.case.summarised


class TestAnExplicitRequestMidFix:
    def test_registers_with_its_reason(self, fixing):
        from agent.decide.rules import case_rule

        state, rt, tracer = fixing
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Užregistruokit meistrą, nenoriu daugiau"
        case_rule.plan(state, rt)  # the conclusion turn
        case_rule.plan(state, rt)

        assert "technician_demanded" in tracer.moves()
        assert state.ticket.reason == "klientas_praso"

    @pytest.mark.parametrize(
        "said", ["Nereikia registruoti", "Ne, nereikia meistro", "Nenoriu registruoti"]
    )
    def test_a_refused_registration_is_not_a_request(self, said):
        from agent.perceive.detectors import detect_refuse_or_ticket

        assert detect_refuse_or_ticket(said) != "demand"


def test_the_reason_survives_the_conclusion_turn(fixing):
    """Bug in e190fd9: `_escalate` sums up first and registers on the next turn — the second
    call fell back to the default reason."""
    from agent.decide.rules.case_rule import _escalate

    state, rt, _ = fixing
    state.case.worked = ["check_lights"]  # something was done — so there is a conclusion turn
    _escalate(state, rt, state.case.fault, why="nesusikalbame")  # the conclusion
    assert state.ticket.stage is None
    _escalate(state, rt, state.case.fault)  # the registration, no reason passed
    assert state.ticket.reason == "nesusikalbame"


class TestPhoneWorkFirstOfferedOnce:
    """Andrius (2026-10-14): the agent's aim is to fix it by phone; the only motivation is „we
    can fix it now". Phone work the card needs before a technician is OFFERED once; the caller's
    answer decides; the ticket says what was not done; nothing about a price."""

    @pytest.fixture
    def hung(self, make_state, make_runtime):
        from agent.ledger import record_client, record_telemetry

        tracer = _Tracer()
        state, rt = make_state("+37060020112"), make_runtime(tracer=tracer)
        state.identity.customer_id = "CUST112"
        record_telemetry(state, rt, {**BASE, "traffic": "none"})
        record_client(state, rt, "fail_scope", "all")
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 0
        return state, rt, tracer

    def _demand(self, hung):
        from agent.decide.rules import case_rule

        state, rt, _ = hung
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Užregistruokit meistrą, nenoriu pats krapštytis"
        return case_rule.plan(state, rt)

    def test_the_offer_says_fix_it_now_and_no_price(self, hung):
        plan = self._demand(hung)

        assert plan.rule == "case.phone_work_offer"
        assert "per minutę" in plan.say.text and "perkrovimas" in plan.say.text
        assert "kain" not in plan.say.text and "mokam" not in plan.say.text

    def test_declined_registers_and_says_what_was_not_done(self, hung):
        from agent.decide.rules import case_rule

        state, rt, tracer = hung
        self._demand(hung)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Ne, tiesiog registruokit"
        case_rule.plan(state, rt)  # the conclusion
        case_rule.plan(state, rt)  # the registration starts

        assert "phone_work_declined" in tracer.moves()
        assert state.ticket.reason == "klientas_nenori"
        assert "perkrauti dabar nenorėjote" in (state.case.summary or {}).get("nepavyko", "")
        assert "_ticket_note" not in state.case.facts  # no „perkrauta, neatsistatė"

    def test_accepted_goes_back_to_the_fix(self, hung):
        from agent.decide.rules import case_rule

        state, rt, tracer = hung
        self._demand(hung)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Gerai, pabandom"
        case_rule.plan(state, rt)

        assert "phone_work_accepted" in tracer.moves()
        assert state.ticket.stage is None and not state.case.summarised

    def test_offered_only_once(self, hung):
        from agent.decide.rules import case_rule

        state, rt, _ = hung
        self._demand(hung)
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Gerai, pabandom"
        case_rule.plan(state, rt)
        plan = self._demand(hung)  # asks again later

        assert plan.rule != "case.phone_work_offer"
