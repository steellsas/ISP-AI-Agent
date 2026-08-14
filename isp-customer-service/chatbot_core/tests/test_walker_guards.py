"""
Walker guard chain (agent/walker_guards.py) — R3 extraction tests.

The chain ORDER is load-bearing (roadmap §5): the order test freezes it so a
refactor cannot silently reorder hard-earned live-call fixes. Behaviour tests
use the REAL strategies and detectors — only the engine is faked.
"""

from types import SimpleNamespace

from agent import walker_guards
from agent.resolution import STRATEGIES, detect_refuse_or_ticket


class GuardEngine:
    """Minimal engine surface the guards touch, with recorded routing calls."""

    def __init__(self):
        self._resume_hold = False
        self._end_confirm_pending = False
        self.routed = []
        self.gotos = []
        self.dialogue_started = []
        self.tracer = SimpleNamespace(emit=lambda *a, **k: None)

    def _route_to(self, r, target):
        self.routed.append(target)

    def _goto_step(self, r, target):
        self.gotos.append(target)

    def _begin_ticket_dialogue(self, step):
        self.dialogue_started.append(step)

    def _evidence_question_open(self):
        return False

    def _asked_recently(self, r):
        return True

    def _classify_confirm_and_route(self, step, strat, user_input):
        return False

    def _classify_instruct_and_advance(self, step, strat, user_input):
        return False


def _strat(verdict="foreign_mac"):
    return STRATEGIES[verdict]


class TestChainOrder:
    def test_prelude_order_is_frozen(self):
        assert [g.__name__ for g in walker_guards.PRELUDE_GUARDS] == [
            "resume_hold",
            "end_confirm_pending",
        ]

    def test_step_guard_order_is_frozen(self):
        assert [g.__name__ for g in walker_guards.STEP_GUARDS] == [
            "device_change_pre_answer",
            "backchannel_hold",
            "restored_pre_answer",
            "refuse_or_ticket_redirect",
            "evidence_question_open_hold",
            "classifier_confirm_route",
            "classifier_instruct_route",
        ]


class TestPrelude:
    def test_resume_hold_consumes_exactly_one_turn(self):
        engine = GuardEngine()
        engine._resume_hold = True
        assert walker_guards.resume_hold(engine, "ne, tęskime") is True
        assert engine._resume_hold is False
        assert walker_guards.resume_hold(engine, "toliau") is False

    def test_end_confirm_pending_holds(self):
        engine = GuardEngine()
        engine._end_confirm_pending = True
        assert walker_guards.end_confirm_pending(engine, "Ne, nenoriu") is True


class TestStepGuards:
    def test_device_change_pre_answer_routes_yes(self):
        engine = GuardEngine()
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        assert step is not None
        r = {"verdict": "foreign_mac", "step": step.id}
        consumed = walker_guards.device_change_pre_answer(
            engine, r, strat, step, "neveikia, keičiau routerį"
        )
        assert consumed is True
        assert engine.routed  # advanced towards the bind step

    def test_backchannel_holds_confirm_step(self):
        engine = GuardEngine()
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id}
        assert walker_guards.backchannel_hold(engine, r, strat, step, "Mhm.") is True
        assert engine.routed == []

    def test_ticket_demand_redirects_to_escalate_and_starts_dialogue(self):
        engine = GuardEngine()
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id}
        phrase = "Nieko nedarysiu, užregistruokite gedimą."
        assert detect_refuse_or_ticket(phrase) == "demand"  # precondition on the real detector
        consumed = walker_guards.refuse_or_ticket_redirect(engine, r, strat, step, phrase)
        assert consumed is True
        assert engine.gotos == ["escalate"]
        assert engine.dialogue_started  # demand IS the consent — dialogue begins now
        assert "paprašė registracijos" in r["escalate_reason"]

    def test_plain_answer_passes_every_guard(self):
        """A normal asked-step answer must fall through the whole chain to the
        walker's advancement dispatch (classifiers report not-consumed here)."""
        engine = GuardEngine()
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id, "asked": True}
        for guard in walker_guards.STEP_GUARDS:
            assert guard(engine, r, strat, step, "Ne, routerio nekeičiau.") is False
