"""STRUKTURA_V3 stage 2 — the phase in shadow: computed from the state the rules leave,
traced every turn, read by no rule."""

import pytest
from agent import phase


class _Tracer:
    session_id = "phase"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def call(make_state, make_runtime):
    tracer = _Tracer()
    return make_state("+37060012353"), make_runtime(tracer=tracer), tracer


def _set(state, **marks):
    s = state
    if marks.get("heard"):
        s.dialog.last_heard = "Neveikia internetas"
    if marks.get("problem"):
        s.intake.problem_type = "internet_down"
    if marks.get("customer"):
        s.identity.customer_id = "CUST009"
    if marks.get("name_owed"):
        s.identity.result_pending = True
    if marks.get("fault"):
        s.case.fault, s.case.solution = "no_mac_observed", 0
    if marks.get("news"):
        s.diagnosis.news_delivered = True
    if marks.get("ticket"):
        s.ticket.stage = "phone"
    if marks.get("closed"):
        s.closing.case_closed = True


@pytest.mark.parametrize(
    ("marks", "expected"),
    [
        ({}, phase.GREETING),
        ({"heard": 1}, phase.INTAKE),
        ({"heard": 1, "problem": 1}, phase.IDENTIFY),
        ({"heard": 1, "problem": 1, "customer": 1, "name_owed": 1}, phase.IDENTIFY),
        ({"heard": 1, "problem": 1, "customer": 1}, phase.INVESTIGATE),
        ({"heard": 1, "problem": 1, "customer": 1, "fault": 1}, phase.INVESTIGATE),
        # the debt told IS the ending; a fault never is (wave 10, S1)
        ({"heard": 1, "problem": 1, "customer": 1, "news": 1}, phase.CLOSING),
        ({"heard": 1, "problem": 1, "customer": 1, "fault": 1, "news": 1}, phase.INVESTIGATE),
        ({"heard": 1, "problem": 1, "customer": 1, "ticket": 1}, phase.TICKET),
        ({"heard": 1, "problem": 1, "customer": 1, "ticket": 1, "closed": 1}, phase.CLOSING),
    ],
)
def test_phase_of(call, marks, expected):
    state, _, _ = call
    _set(state, **marks)
    assert phase.phase_of(state) == expected


def test_observe_traces_moves_and_counts_turns(call):
    state, rt, tracer = call
    phase.observe(state, rt)  # greeting
    _set(state, heard=1, problem=1)
    phase.observe(state, rt)
    phase.observe(state, rt)

    moves = [
        (e["prev"], e["phase"], e["ok"], e["turns_in_phase"])
        for e in tracer.events
        if e["type"] == "phase"
    ]
    assert moves == [
        (None, "greeting", True, 1),
        ("greeting", "identify", True, 1),
        ("identify", "identify", True, 2),
    ]
    assert state.dialog.phase_path == ["greeting", "identify"]


def test_a_move_v3_does_not_allow_is_flagged(call):
    state, rt, tracer = call
    state.dialog.phase = phase.TICKET
    _set(state, heard=1)  # back to intake from a ticket — no v3 owner would do that
    phase.observe(state, rt)
    assert [e for e in tracer.events if e["type"] == "phase"][-1]["ok"] is False


def test_every_phase_has_its_moves():
    assert set(phase.ALLOWED) == set(phase.PHASES)
    for targets in phase.ALLOWED.values():
        assert targets <= set(phase.PHASES)


def test_the_dashboard_draws_the_phases():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "src" / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "js" / "brain.js").read_text(encoding="utf-8")
    assert html.count('class="b-phases"') == 2  # live call and archive
    for key in phase.PHASES:
        assert f'"{key}"' in js


class TestHangUpWithATechnicianDecided:
    """Andrius 2026-10-09: a hang-up during the fault fix still gets its ticket — with what was
    done and when the caller put the receiver down. Eval S4/A1 had closed it as „resolved",
    because a bridged computer makes the line look healthy."""

    def _call(self, make_state, make_runtime, created):
        def tools(name, args):
            if name == "create_ticket":
                created.append(args)
                return {"success": True, "ticket_id": "TKT-HANG"}
            if name == "diagnose_connection":
                return {"verdict": None}  # the bridge: traffic flows, nothing to report
            return {}

        tracer = _Tracer()
        state, rt = make_state("+37060012353"), make_runtime(fake_tools=tools, tracer=tracer)
        state.identity.customer_id = "CUST009"
        state.intake.problem_type = "internet_down"
        state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
        state.case.fault, state.case.solution = "no_mac_observed", 0
        state.dialog.phase = phase.TICKET
        return state, rt, tracer

    def test_the_ticket_is_registered_with_the_hang_up(self, make_state, make_runtime):
        from agent.call_record import finalizer

        created = []
        state, rt, tracer = self._call(make_state, make_runtime, created)
        state.case.summarised = True
        state.ticket.stage = "phone"  # the contact questions were running
        finalizer.finalize(state, rt)

        assert state.ticket.ticket_id == "TKT-HANG"
        assert state.closing.closed_reason == "registered"
        description = created[0]["problem_description"]
        assert "padėjo ragelį" in description and "registruojant gedimą" in description
        assert any(e.get("action") == "registration_decided" for e in tracer.events)

    def test_a_healthy_line_without_a_decision_is_still_resolved(self, make_state, make_runtime):
        from agent.call_record import finalizer

        created = []
        state, rt, _ = self._call(make_state, make_runtime, created)
        state.dialog.phase = phase.INVESTIGATE
        finalizer.finalize(state, rt)

        assert created == []
        assert state.closing.closed_reason == "resolved"
