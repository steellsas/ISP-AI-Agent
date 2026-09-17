"""Hypothesis stability (D-05): a contradiction only puts the belief in doubt; its confirm
question moves it to confirming; the answer returns it to active."""

from agent.decide import hypothesis


class _Tracer:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def _call(make_state, make_runtime):
    tracer = _Tracer()
    return make_state("+37060012353"), make_runtime(tracer=tracer), tracer


def test_contradiction_moves_active_to_doubt_to_confirming_to_active(make_state, make_runtime):
    state, rt, tracer = _call(make_state, make_runtime)
    assert hypothesis.status(state) == "active"
    assert hypothesis.doubt(state, rt, "conflict", "lights", "on", "off")
    assert hypothesis.status(state) == "doubt"
    c = hypothesis.ask(state, rt, "conflict")
    assert (c.fact_key, c.before_value, c.now_value) == ("lights", "on", "off")
    assert hypothesis.status(state) == "confirming"
    assert hypothesis.answered(state, rt, "conflict") is c
    assert hypothesis.status(state) == "active"
    assert [e["status"] for e in tracer.events if e["type"] == "hypothesis"] == [
        "doubt",
        "confirming",
        "active",
    ]


def test_one_contradiction_at_a_time(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    assert hypothesis.doubt(state, rt, "flip", "outlet_works", None, "not_working")
    assert not hypothesis.doubt(state, rt, "conflict", "lights", "on", "off")
    assert state.diagnosis.contradiction.kind == "flip"


def test_a_question_is_answered_only_after_it_was_asked(make_state, make_runtime):
    state, rt, _ = _call(make_state, make_runtime)
    hypothesis.doubt(state, rt, "flip", "outlet_works", None, "not_working")
    assert hypothesis.answered(state, rt, "flip") is None  # still due, not out
    assert hypothesis.ask(state, rt, "conflict") is None  # another kind
    assert hypothesis.ask(state, rt, "flip") is not None
    assert hypothesis.due(state, "flip") is None
