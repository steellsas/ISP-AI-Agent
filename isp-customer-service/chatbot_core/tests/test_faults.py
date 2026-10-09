"""
Tests for the declarative intent knowledge: `knowledge/intents.yaml` is the source for
the call's INTENT (triggers). (The v1 procedure/answer-meaning tests went with the
fault packs.)
"""

from agent.intents import classify_purpose


class TestPurpose:
    def test_triggers_classify_the_reported_problem(self):
        assert classify_purpose("internetas veikia labai lėtai") == "internet_slow"
        assert classify_purpose("neveikia internetas") == "internet_down"
        assert classify_purpose("dėl sąskaitos skambinu") == "billing"

    def test_specific_problem_wins_over_broader_one(self):
        # "lėtai" must beat the broader internet_down triggers — YAML order carries this
        assert classify_purpose("internetas lėtai veikia") == "internet_slow"

    def test_no_match_returns_none(self):
        assert classify_purpose("labas rytas") is None
        assert classify_purpose(None) is None
