"""
Tests for the repeat-guard (ReactAgent stuck counter + deterministic backstop).

Stops the agent re-asking the same question 2–4× (observed in voice traces):
a no-progress question increments stuck_count, real progress resets it, and at
3/4 a deterministic backstop fires BEFORE the LLM (so it works with streaming).

Run: pytest tests/test_repeat_guard.py -v
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent.decide.rules.dialog import stuck_backstop
from agent.dialog_utils import is_question, progress_key, similar
from agent.execute.say import apply_backstop
from agent.speak.postprocess import track_stuck


def _agent():
    from tests.calls import make_agent

    return make_agent("unknown")


def _turn(agent, text=None):
    """One stage turn (perceive, then the narrator with its scripted exits); the reply."""
    from agent.graph_v2.runtime import narrate
    from agent.perceive import perceive

    perceive(agent.state, agent.runtime, text)
    return narrate(agent.state, agent.runtime, text, "diagnosis", "diagnosis", exits=True)


def _stream_of(message):
    """A fake stream_tool_completion: streams the message content, returns the message."""

    def _gen(**kwargs):
        if message.content:
            yield message.content
        return message

    return _gen


class TestQuestionSimilarity:
    def test_is_question(self):
        a = _agent()
        assert is_question("Kurioje gatvėje?") is True
        assert is_question("Radau jūsų adresą.") is False

    def test_apologetic_prefix_is_a_repeat(self):
        # The exact pair from the trace (only "Atsiprašau, " differs).
        a = _agent()
        q1 = "Ar galėtumėte pasakyti, kurioje gatvėje neveikia internetas?"
        q2 = "Atsiprašau, ar galėtumėte pasakyti, kurioje gatvėje neveikia internetas?"
        assert similar(q1, q2) is True

    def test_different_questions_not_similar(self):
        a = _agent()
        assert similar("Kurioje gatvėje neveikia?", "Koks namo numeris?") is False


class TestStuckCounter:
    def test_repeat_increments(self):
        a = _agent()
        a.state.dialog.last_question = "Kurioje gatvėje neveikia internetas?"
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, "Atsiprašau, kurioje gatvėje neveikia internetas?")
        assert a.state.dialog.stuck_count == 1

    def test_first_question_does_not_increment(self):
        # No prior question -> not a repeat -> normal opening, no strike.
        a = _agent()
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, "Kurioje gatvėje neveikia internetas?")
        assert a.state.dialog.stuck_count == 0

    def test_different_question_does_not_increment(self):
        # A new, distinct question is normal progression, not a stuck loop.
        a = _agent()
        a.state.dialog.last_question = "Kurioje gatvėje neveikia internetas?"
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, "Koks namo numeris?")
        assert a.state.dialog.stuck_count == 0

    def test_progress_resets_even_on_repeat(self):
        a = _agent()
        a.state.dialog.stuck_count = 2
        a.state.dialog.last_question = "Kurioje gatvėje?"
        a.state.turn.progress_key_at_start = progress_key(a.state)
        a.state.identity.customer_id = "CUST105"  # the turn advanced
        track_stuck(a.state, a.runtime, "Kurioje gatvėje?")
        assert a.state.dialog.stuck_count == 0

    def test_repeated_verbatim_flag_set(self):
        a = _agent()
        a.state.dialog.last_question = "Kurioje gatvėje neveikia internetas?"
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, "Atsiprašau, kurioje gatvėje neveikia internetas?")
        assert a.state.dialog.last_reply_repeated is True

    def test_apply_backstop_offer_climbs_ladder(self):
        a = _agent()
        a.state.dialog.stuck_count = 3
        apply_backstop(a.state, a.runtime, ("Gal turite abonento kodą?", False))
        assert a.state.dialog.stuck_count == 4

    def test_apply_backstop_unidentified_closes_as_unidentified(self):
        a = _agent()
        a.state.dialog.stuck_count = 4
        text, should_close = stuck_backstop(a.state)
        assert "Užregistruosiu" not in text  # no registration promised without an account
        apply_backstop(a.state, a.runtime, (text, should_close))
        assert a.state.closing.case_closed is True
        assert a.state.closing.closed_reason == "declined"
        assert a.state.closing.unidentified_reason == "stuck"

    def test_apply_backstop_identified_registers_the_promised_ticket(self, db_connection):
        a = _agent()
        a.state.identity.customer_id = "CUST009"
        a.state.resolution.procedure = {"verdict": "router_hung", "step": "rh_check"}
        a.state.dialog.stuck_count = 4
        text, should_close = stuck_backstop(a.state)
        assert "Užregistruosiu" in text
        apply_backstop(a.state, a.runtime, (text, should_close))
        assert a.state.ticket.ticket_id  # F-5: the promise is kept
        assert a.state.closing.closed_reason == "registered"
        assert a.state.resolution.procedure["escalate_reason"] == "stuck"


class TestBackstop:
    def test_none_below_three(self):
        a = _agent()
        a.state.dialog.stuck_count = 2
        assert stuck_backstop(a.state) is None

    def test_offer_code_at_three(self):
        a = _agent()
        a.state.dialog.stuck_count = 3
        text, should_close = stuck_backstop(a.state)
        assert "abonento kodą" in text
        assert should_close is False

    def test_register_and_close_at_four(self):
        a = _agent()
        a.state.dialog.stuck_count = 4
        _text, should_close = stuck_backstop(a.state)
        assert should_close is True

    def test_backstop_fires_before_llm(self, db_connection):
        """At stuck>=3 the engine answers deterministically — no LLM call."""
        a = _agent()
        a.state.dialog.turn_count = 1  # past the greeting turn (a policy plan)
        a.state.dialog.stuck_count = 3
        with patch("agent.react_agent.stream_tool_completion") as stream_mock:
            reply = _turn(a, "nesąmonė")
        stream_mock.assert_not_called()
        assert "abonento kodą" in reply

    def test_backstop_at_four_closes_case(self, db_connection):
        a = _agent()
        a.state.dialog.turn_count = 1  # past the greeting turn (a policy plan)
        a.state.dialog.stuck_count = 4
        with patch("agent.react_agent.stream_tool_completion"):
            _turn(a, "vis dar nesąmonė")
        assert a.state.closing.case_closed is True
        assert a.state.closing.closed_reason == "declined"


class TestProgressReset:
    """The bug that shipped: NLU progress this turn must clear the counter."""

    def test_nlu_street_fill_resets_stuck(self, db_connection):
        a = _agent()
        a.state.dialog.turn_count = 1  # past the greeting turn (a policy plan)
        a.state.dialog.stuck_count = 2
        a.state.intake.problem_type = "internet_down"
        msg = SimpleNamespace(content="Radau gatvę. Koks namo numeris?", tool_calls=None)
        with (
            patch("agent.react_agent.stream_tool_completion", side_effect=_stream_of(msg)),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            _turn(a, "Dainų gatvė")
        assert a.state.identity.profile.street.value  # NLU heard the street this turn
        assert a.state.dialog.stuck_count == 0  # ...which counts as progress and resets


class TestStuckFacts:
    def test_nudge_at_one(self):
        from agent.speak.context_card import context_card

        a = _agent()
        a.state.dialog.stuck_count = 1
        block = context_card(a.state, a.runtime)
        assert block is not None and "neišgirdau" in block.lower()

    def test_escalation_at_two(self):
        from agent.speak.context_card import context_card

        a = _agent()
        a.state.dialog.stuck_count = 2
        block = context_card(a.state, a.runtime)
        assert block is not None and "abonento kodą" in block
