"""The analyst's typed signals (M5, D-06): schema, application, and its boundaries."""

from unittest.mock import patch

import pytest
from agent.analyst.node import apply, read, run_sync
from agent.analyst.signals import Signal, parse


def _signal(**kw):
    return Signal(**{"confidence": 0.9, "turn_index": 0, **kw})


class TestSchema:
    def test_valid_json_becomes_signals(self):
        raw = (
            '{"signals": [{"type": "frustration", "quote": "jau trečią kartą", "confidence": 0.8}]}'
        )

        signals = parse(raw, turn_index=3)

        assert [s.type for s in signals] == ["frustration"]
        assert signals[0].turn_index == 3

    def test_an_unknown_type_is_dropped(self):
        raw = '{"signals": [{"type": "diagnosis", "confidence": 0.9}]}'

        assert parse(raw, turn_index=1) == []

    def test_a_low_confidence_signal_is_dropped(self):
        raw = '{"signals": [{"type": "off_topic", "confidence": 0.2}]}'

        assert parse(raw, turn_index=1) == []

    def test_garbage_never_breaks_the_call(self):
        assert parse("not json at all", turn_index=1) == []
        assert parse(None, turn_index=1) == []

    def test_a_fenced_block_still_parses(self):
        raw = '```json\n{"signals": [{"type": "frustration", "confidence": 0.9}]}\n```'

        assert [s.type for s in parse(raw, turn_index=1)] == ["frustration"]


class TestApply:
    """Each signal goes to the machinery that owns that decision — never straight in."""

    def test_a_contradiction_puts_the_belief_in_doubt(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.diagnosis.evidence["lights"] = {"value": "on", "source": "client", "turn": 1}

        apply(state, rt, [_signal(type="contradiction", fact_key="lights", value="off")])

        c = state.diagnosis.contradiction
        assert c is not None and c.source == "analyst" and c.fact_key == "lights"
        assert c.before_value == "on" and c.now_value == "off"
        assert state.diagnosis.evidence["lights"]["value"] == "on"  # the fact is untouched

    def test_a_contradiction_about_an_unknown_fact_is_ignored(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()

        apply(state, rt, [_signal(type="contradiction", fact_key="lights", value="off")])

        assert state.diagnosis.contradiction is None

    def test_an_already_answered_fact_becomes_a_confirm(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()

        apply(
            state,
            rt,
            [_signal(type="already_answered", fact_key="scope", value="all", quote="visuose")],
        )

        c = state.diagnosis.contradiction
        assert c is not None and c.kind == "flip" and c.now_value == "all"
        assert "scope" not in state.diagnosis.evidence  # the analyst writes no facts

    def test_a_secondary_problem_reaches_the_closing_list(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()

        apply(state, rt, [_signal(type="secondary_problem", quote="dar televizija stringa")])

        assert state.intake.secondary_problems == [
            {"type": None, "text": "dar televizija stringa", "source": "analyst"}
        ]

    def test_tone_signals_only_reach_the_speaker(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()

        apply(state, rt, [_signal(type="frustration", quote="jau nebeturiu kantrybės")])

        assert state.diagnosis.contradiction is None
        assert state.voice.analyst_signals[0]["type"] == "frustration"

    def test_a_stale_signal_is_dropped(self, make_state, make_runtime):
        """The async read races the caller: signals about an older turn are worthless."""
        state, rt = make_state("+37060020112"), make_runtime()
        state.dialog.turn_count = 5

        apply(state, rt, [_signal(type="frustration", turn_index=1)])

        assert state.voice.analyst_signals is None


class TestTheCardShowsTone:
    def test_frustration_reaches_the_card_once(self, make_state, make_runtime):
        from agent.speak.context_card import context_card

        state, rt = make_state("+37060020112"), make_runtime()
        state.voice.analyst_signals = [{"type": "frustration", "quote": "kiek galima"}]

        card = context_card(state, rt)

        assert "TONE:" in card and "kiek galima" in card
        assert state.voice.analyst_signals is None
        assert "TONE:" not in (context_card(state, rt) or "")


class TestModes:
    def test_off_reads_nothing(self, make_state, make_runtime, monkeypatch):
        monkeypatch.setenv("ANALYST_MODE", "off")
        state, rt = make_state("+37060020112"), make_runtime()
        state.intake.problem_type = "internet_down"

        assert read(state, rt) == []

    def test_sync_reads_and_applies_at_the_end_of_the_turn(
        self, make_state, make_runtime, monkeypatch
    ):
        monkeypatch.setenv("ANALYST_MODE", "sync")
        state, rt = make_state("+37060020112"), make_runtime()
        state.intake.problem_type = "internet_down"
        raw = '{"signals": [{"type": "frustration", "quote": "kiek galima", "confidence": 0.9}]}'

        with patch("src.services.llm.client.llm_completion", return_value=raw):
            run_sync(state, rt)

        assert state.voice.analyst_signals[0]["type"] == "frustration"

    def test_async_does_not_run_in_the_turn(self, make_state, make_runtime, monkeypatch):
        monkeypatch.setenv("ANALYST_MODE", "async")
        state, rt = make_state("+37060020112"), make_runtime()
        state.intake.problem_type = "internet_down"

        with patch("src.services.llm.client.llm_completion", side_effect=AssertionError("called")):
            run_sync(state, rt)

        assert state.voice.analyst_signals is None


class TestWiring:
    def test_the_turn_ends_with_the_analyst_read(self, make_state, make_runtime, monkeypatch):
        """Sync mode: narrate() closes the turn with the read, and the signals land."""
        from types import SimpleNamespace

        from agent.analyst import node as analyst_node
        from agent.graph_v2.runtime import narrate

        monkeypatch.setenv("ANALYST_MODE", "sync")
        state, rt = make_state("+37060020112"), make_runtime()
        state.intake.problem_type = "internet_down"
        monkeypatch.setattr(
            analyst_node, "read", lambda s, r: [_signal(type="frustration", quote="kiek galima")]
        )

        def _stream(**kwargs):
            yield "Gerai."
            return SimpleNamespace(content="Gerai.", tool_calls=None)

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            narrate(state, rt, "taip", "diagnosis", "diagnosis")

        assert state.voice.analyst_signals[0]["type"] == "frustration"


class TestBackgroundWindow:
    """A voice call reads the analyst in its background thread — no reply waits for it."""

    def test_a_call_with_a_background_window_is_async(self, make_state, make_runtime, monkeypatch):
        from agent.analyst.node import mode

        monkeypatch.delenv("ANALYST_MODE", raising=False)
        state = make_state("+37060020112")

        assert mode(state) == "sync"
        state.voice.background_reads = True
        assert mode(state) == "async"

    def test_an_explicit_mode_wins(self, make_state, monkeypatch):
        from agent.analyst.node import mode

        monkeypatch.setenv("ANALYST_MODE", "off")
        state = make_state("+37060020112")
        state.voice.background_reads = True

        assert mode(state) == "off"

    def test_the_turn_does_not_read_in_a_background_call(
        self, make_state, make_runtime, monkeypatch
    ):
        from agent.analyst.node import run_sync

        monkeypatch.delenv("ANALYST_MODE", raising=False)
        state, rt = make_state("+37060020112"), make_runtime()
        state.intake.problem_type = "internet_down"
        state.voice.background_reads = True

        with patch("src.services.llm.client.llm_completion", side_effect=AssertionError("called")):
            run_sync(state, rt)

        assert state.voice.analyst_signals is None


# (what the call is doing, does the analyst read this turn?)
DUE = [
    ({"turn": 3}, True),  # the routine read (every analyst_every_turns)
    ({"turn": 4}, False),  # nothing for it: perception read this turn
    ({"turn": 4, "stuck": 1}, True),  # stuck — the cross-turn view is the point
    ({"turn": 4, "repeated": True}, True),
    ({"turn": 4, "ticket": "phone"}, True),  # before the call ends
    ({"turn": 4, "debt_offer": "asked"}, True),
    # a chosen solution is not a trigger by itself: it stays true for the rest of the
    # call, which would mean a read every turn again.
    ({"turn": 4, "solution": True}, False),
]


@pytest.mark.parametrize("call, reads", DUE)
def test_the_analyst_reads_when_its_view_matters(call, reads, make_state):
    """Wave 2a: the analyst was the most expensive call of every turn (the full
    transcript) — as many reads as replies."""
    from agent.analyst.node import due

    state = make_state("+37060020112")
    state.dialog.turn_count = call["turn"]
    state.dialog.stuck_count = call.get("stuck", 0)
    state.dialog.last_reply_repeated = call.get("repeated", False)
    state.ticket.stage = call.get("ticket")
    state.closing.debt_offer = call.get("debt_offer")
    if call.get("solution"):
        state.resolution.procedure = {"verdict": "router_hung", "solution_synced": "rh_reboot"}

    assert due(state) is reads


def test_a_read_that_is_not_due_calls_no_model(make_state, make_runtime, monkeypatch):
    from agent.analyst.node import read

    monkeypatch.setenv("ANALYST_MODE", "sync")
    state, rt = make_state("+37060020112"), make_runtime()
    state.intake.problem_type = "internet_down"
    state.dialog.turn_count = 4  # not a routine read turn

    with patch("src.services.llm.client.llm_completion", side_effect=AssertionError("called")):
        assert read(state, rt) == []
