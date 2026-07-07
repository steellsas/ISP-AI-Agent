"""
Tests for the repeat-guard (ReactAgent stuck counter + deterministic backstop).

Stops the agent re-asking the same question 2–4× (observed in voice traces):
a no-progress question increments stuck_count, real progress resets it, and at
3/4 a deterministic backstop fires BEFORE the LLM (so it works with streaming).

Run: pytest tests/test_repeat_guard.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch


def _agent():
    from agent.react_agent import ReactAgent

    return ReactAgent(caller_phone="unknown")


class TestQuestionSimilarity:
    def test_is_question(self):
        a = _agent()
        assert a._is_question("Kurioje gatvėje?") is True
        assert a._is_question("Radau jūsų adresą.") is False

    def test_apologetic_prefix_is_a_repeat(self):
        # The exact pair from the trace (only "Atsiprašau, " differs).
        a = _agent()
        q1 = "Ar galėtumėte pasakyti, kurioje gatvėje neveikia internetas?"
        q2 = "Atsiprašau, ar galėtumėte pasakyti, kurioje gatvėje neveikia internetas?"
        assert a._similar(q1, q2) is True

    def test_different_questions_not_similar(self):
        a = _agent()
        assert a._similar("Kurioje gatvėje neveikia?", "Koks namo numeris?") is False


class TestStuckCounter:
    def test_repeat_increments(self):
        a = _agent()
        a.state.last_question = "Kurioje gatvėje neveikia internetas?"
        a._turn_start_key = a._progress_key()
        a._track_stuck("Atsiprašau, kurioje gatvėje neveikia internetas?")
        assert a.state.stuck_count == 1

    def test_first_question_does_not_increment(self):
        # No prior question -> not a repeat -> normal opening, no strike.
        a = _agent()
        a._turn_start_key = a._progress_key()
        a._track_stuck("Kurioje gatvėje neveikia internetas?")
        assert a.state.stuck_count == 0

    def test_different_question_does_not_increment(self):
        # A new, distinct question is normal progression, not a stuck loop.
        a = _agent()
        a.state.last_question = "Kurioje gatvėje neveikia internetas?"
        a._turn_start_key = a._progress_key()
        a._track_stuck("Koks namo numeris?")
        assert a.state.stuck_count == 0

    def test_progress_resets_even_on_repeat(self):
        a = _agent()
        a.state.stuck_count = 2
        a.state.last_question = "Kurioje gatvėje?"
        a._turn_start_key = a._progress_key()
        a.state.customer_id = "CUST105"  # the turn advanced
        a._track_stuck("Kurioje gatvėje?")
        assert a.state.stuck_count == 0

    def test_repeated_verbatim_flag_set(self):
        a = _agent()
        a.state.last_question = "Kurioje gatvėje neveikia internetas?"
        a._turn_start_key = a._progress_key()
        a._track_stuck("Atsiprašau, kurioje gatvėje neveikia internetas?")
        assert a._repeated_verbatim is True

    def test_apply_backstop_offer_climbs_ladder(self):
        a = _agent()
        a.state.stuck_count = 3
        a._apply_backstop(("Gal turite abonento kodą?", False))
        assert a.state.stuck_count == 4

    def test_apply_backstop_register_closes(self):
        a = _agent()
        a.state.stuck_count = 4
        a._apply_backstop(("Užregistruosiu jūsų problemą.", True))
        assert a.state.case_closed is True
        assert a.state.closed_reason == "declined"


class TestBackstop:
    def test_none_below_three(self):
        a = _agent()
        a.state.stuck_count = 2
        assert a._stuck_backstop() is None

    def test_offer_code_at_three(self):
        a = _agent()
        a.state.stuck_count = 3
        text, should_close = a._stuck_backstop()
        assert "abonento kodą" in text
        assert should_close is False

    def test_register_and_close_at_four(self):
        a = _agent()
        a.state.stuck_count = 4
        _text, should_close = a._stuck_backstop()
        assert should_close is True

    def test_backstop_fires_before_llm(self, db_connection):
        """At stuck>=3 the engine answers deterministically — no LLM call."""
        a = _agent()
        a.run_until_response()  # greeting (turn 0)
        a.state.stuck_count = 3
        with (
            patch("agent.react_agent.llm_tool_completion") as llm_mock,
            patch("agent.react_agent.stream_tool_completion") as stream_mock,
        ):
            reply = a.run_until_response("nesąmonė")
        llm_mock.assert_not_called()
        stream_mock.assert_not_called()
        assert "abonento kodą" in reply

    def test_backstop_at_four_closes_case(self, db_connection):
        a = _agent()
        a.run_until_response()
        a.state.stuck_count = 4
        with patch("agent.react_agent.llm_tool_completion"):
            a.run_until_response("vis dar nesąmonė")
        assert a.state.case_closed is True
        assert a.state.closed_reason == "declined"


class TestProgressReset:
    """The bug that shipped: NLU progress this turn must clear the counter."""

    def test_nlu_street_fill_resets_stuck(self, db_connection):
        a = _agent()
        a.run_until_response()  # greeting
        a.state.stuck_count = 2
        a.state.problem_type = "internet_down"
        msg = SimpleNamespace(content="Radau gatvę. Koks namo numeris?", tool_calls=None)
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            a.run_until_response("Dainų gatvė")
        assert a.state.profile.street.value  # NLU heard the street this turn
        assert a.state.stuck_count == 0  # ...which counts as progress and resets


class TestStuckFacts:
    def test_nudge_at_one(self):
        a = _agent()
        a.state.stuck_count = 1
        block = a._state_facts_block()
        assert block is not None and "neišgirdau" in block.lower()

    def test_escalation_at_two(self):
        a = _agent()
        a.state.stuck_count = 2
        block = a._state_facts_block()
        assert block is not None and "abonento kodą" in block
