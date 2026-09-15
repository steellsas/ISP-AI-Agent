"""
Walker guard chain (agent/procedure_guards.py) — R3 extraction tests.

The chain ORDER is load-bearing (roadmap §5): the order test freezes it so a
refactor cannot silently reorder hard-earned live-call fixes. Behaviour tests
use the REAL strategies and detectors — only the engine is faked.
"""

from types import SimpleNamespace

from agent.decide import procedure_guards
from agent.graph_v2.state import GraphState
from agent.perceive.detectors import detect_refuse_or_ticket
from agent.resolution import get_strategy


class GuardEngine:
    """Minimal call surface the guards touch: a real state, a runtime, and the
    routing/dialogue flows replaced by recorders."""

    def __init__(self, monkeypatch):
        self.state = GraphState()
        self.routed = []
        self.gotos = []
        self.dialogue_started = []
        self.tracer = SimpleNamespace(emit=lambda *a, **k: None)
        self.runtime = SimpleNamespace(tracer=self.tracer, engine=self)
        recorders = {
            "agent.decide.procedure.route_to": lambda state, rt, r, target: self.routed.append(
                target
            ),
            "agent.decide.procedure.goto_step": lambda state, rt, r, target: self.gotos.append(
                target
            ),
            "agent.ticket_flow.begin_ticket_dialogue": (
                lambda state, rt, step: self.dialogue_started.append(step)
            ),
            "agent.evidence_drive.evidence_question_open": lambda state, rt: False,
            "agent.decide.procedure.classify_confirm_and_route": lambda state, rt, *a: False,
            "agent.decide.procedure.classify_instruct_and_advance": lambda state, rt, *a: False,
        }
        for target, fake in recorders.items():
            monkeypatch.setattr(target, fake)


def _strat(verdict="foreign_mac"):
    return get_strategy(verdict)


class TestChainOrder:
    def test_prelude_order_is_frozen(self):
        # B perjungimas (2026-09-08): registro prioritetų guard'as PIRMAS —
        # aukštesnio savininko klausimas valdo turn'ą prieš bet ką kitą.
        assert [g.__name__ for g in procedure_guards.PRELUDE_GUARDS] == [
            "question_priority_hold",
            "resume_hold",
            "end_confirm_pending",
        ]

    def test_step_guard_order_is_frozen(self):
        assert [g.__name__ for g in procedure_guards.STEP_GUARDS] == [
            "device_change_pre_answer",
            "homework_consent",
            "backchannel_hold",
            "restored_pre_answer",
            "refuse_or_ticket_redirect",
            "evidence_question_open_hold",
            "classifier_confirm_route",
            "classifier_instruct_route",
        ]


class TestPrelude:
    def test_resume_hold_consumes_exactly_one_turn(self, monkeypatch):
        engine = GuardEngine(monkeypatch)
        engine.state.dialog.resume_hold_due = True
        assert procedure_guards.resume_hold(engine.state, engine.runtime, "ne, tęskime") is True
        assert engine.state.dialog.resume_hold_due is False
        assert procedure_guards.resume_hold(engine.state, engine.runtime, "toliau") is False

    def test_end_confirm_pending_holds(self, monkeypatch):
        engine = GuardEngine(monkeypatch)
        engine.state.dialog.end_confirm_pending = True
        assert (
            procedure_guards.end_confirm_pending(engine.state, engine.runtime, "Ne, nenoriu")
            is True
        )


class TestStepGuards:
    def test_device_change_pre_answer_routes_yes(self, monkeypatch):
        engine = GuardEngine(monkeypatch)
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        assert step is not None
        r = {"verdict": "foreign_mac", "step": step.id}
        consumed = procedure_guards.device_change_pre_answer(
            engine.state, engine.runtime, r, strat, step, "neveikia, keičiau routerį"
        )
        assert consumed is True
        assert engine.routed  # advanced towards the bind step

    def test_backchannel_holds_confirm_step(self, monkeypatch):
        engine = GuardEngine(monkeypatch)
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id}
        assert (
            procedure_guards.backchannel_hold(engine.state, engine.runtime, r, strat, step, "Mhm.")
            is True
        )
        assert engine.routed == []

    def test_ticket_demand_redirects_to_escalate_and_starts_dialogue(self, monkeypatch):
        engine = GuardEngine(monkeypatch)
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id}
        phrase = "Nieko nedarysiu, užregistruokite gedimą."
        assert detect_refuse_or_ticket(phrase) == "demand"  # precondition on the real detector
        consumed = procedure_guards.refuse_or_ticket_redirect(
            engine.state, engine.runtime, r, strat, step, phrase
        )
        assert consumed is True
        assert engine.gotos == ["escalate"]
        assert engine.dialogue_started  # demand IS the consent — dialogue begins now
        assert r["escalate_reason"] == "caller_asked_ticket"

    def test_plain_answer_passes_every_guard(self, monkeypatch):
        """A normal asked-step answer must fall through the whole chain to the
        walker's advancement dispatch (classifiers report not-consumed here)."""
        engine = GuardEngine(monkeypatch)
        strat = _strat("foreign_mac")
        step = strat.step("confirm_change")
        r = {"verdict": "foreign_mac", "step": step.id, "asked": True}
        for guard in procedure_guards.STEP_GUARDS:
            assert (
                guard(engine.state, engine.runtime, r, strat, step, "Ne, routerio nekeičiau.")
                is False
            )
