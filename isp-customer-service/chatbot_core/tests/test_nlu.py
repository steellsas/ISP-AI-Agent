"""
Tests for the deterministic problem and symptom readers (agent/perceive/nlu.py).

The ADDRESS reader moved to tests/identification/test_address_reading.py (ROADMAP 3.2); the
problem/symptom readers follow in stage 3.4 (tests by function for the other phases).
"""

import pytest


class TestClassifyProblem:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("neveikia internetas", "internet_down"),
            ("nėra interneto man", "internet_down"),
            ("internetas labai lėtas", "internet_slow"),
            ("viskas stringa ir buferiuoja", "internet_slow"),
            ("neveikia televizija", "tv"),
            ("klausimas dėl sąskaitos", "billing"),
            ("noriu sumokėti", "billing"),
            ("labas, kaip sekasi", None),
        ],
    )
    def test_keyword_classification(self, text, expected):
        from agent.perceive.nlu import classify_problem

        assert classify_problem(text) == expected

    def test_slow_beats_down(self):
        """'lėtas internetas' is slow, not down (specific keyword first)."""
        from agent.perceive.nlu import classify_problem

        assert classify_problem("internetas lėtas") == "internet_slow"


class TestExtractSymptoms:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("lemputės nedega", {"lights": "off"}),
            ("routerio lemputės dega žaliai", {"lights": "on"}),
            ("lemputė mirksi", {"lights": "blinking"}),
            ("jungiuosi per wifi", {"connection": "wifi"}),
            ("prijungta laidu", {"connection": "wired"}),
            ("neveikia visuose įrenginiuose", {"devices": "all"}),
            ("internetas dingsta kartais", {"frequency": "intermittent"}),
            ("dar ir televizija neveikia", {"services": "tv"}),
            ("lamputės nedaga", {"lights": "off"}),  # STT misspelling (live)
            ("lemputės dagą", {"lights": "on"}),  # STT misspelling (live)
            ("labas", {}),
        ],
    )
    def test_categorical_symptoms(self, text, expected):
        from agent.perceive.nlu import extract_symptoms

        assert extract_symptoms(text) == expected

    def test_negation_beats_positive(self):
        """'nedega' must win over the substring 'dega'."""
        from agent.perceive.nlu import extract_symptoms

        assert extract_symptoms("lemputės nedega")["lights"] == "off"

    def test_multiple_categories(self):
        from agent.perceive.nlu import extract_symptoms

        got = extract_symptoms("per wifi, lemputės nedega")
        assert got == {"connection": "wifi", "lights": "off"}


def _stream_of(message):
    """A fake stream_tool_completion: streams the message content, returns the message."""

    def _gen(**kwargs):
        if message.content:
            yield message.content
        return message

    return _gen


class TestPrefillWiring:
    def test_symptoms_prefilled_and_surfaced(self, db_connection):
        """A symptom turn populates state.symptoms and the facts block (A3)."""
        from unittest.mock import patch

        from agent.perceive import perceive
        from agent.speak.context_card import context_card
        from agent.speak.node import turn as speak_turn

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.state.dialog.turn_count = 1

        msg = type("M", (), {"content": "Gerai.", "tool_calls": None})()
        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream_of(msg)),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            text = "internetas neveikia, lemputės nedega, jungiuosi per wifi"
            perceive(agent.state, agent.runtime, text)
            list(speak_turn(agent.state, agent.runtime, text, "intake"))

        assert agent.state.intake.symptoms["lights"] == "off"
        assert agent.state.intake.symptoms["connection"] == "wifi"
        facts = context_card(agent.state, agent.runtime)
        assert "SYMPTOMS" in facts and "lights=off" in facts
