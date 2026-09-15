"""
Tests for the declarative fault knowledge (Phase 3.8 step 5b/5c).

`knowledge/faults.yaml` is now the source for the call's PURPOSE (triggers), the
PROCEDURE (steps) and the DETECTION meanings (answers).
"""

from agent.faults import build_strategy, classify_purpose, step_options
from agent.resolution import get_strategy


class TestPurpose:
    def test_triggers_classify_the_reported_problem(self):
        assert classify_purpose("internetas veikia labai lėtai") == "internet_slow"
        assert classify_purpose("neveikia internetas") == "internet_down"
        assert classify_purpose("dėl sąskaitos skambinu") == "saskaitos"

    def test_specific_problem_wins_over_broader_one(self):
        # "lėtai" must beat the broader internet_down triggers — YAML order carries this
        assert classify_purpose("internetas lėtai veikia") == "internet_slow"

    def test_no_match_returns_none(self):
        assert classify_purpose("labas rytas") is None
        assert classify_purpose(None) is None


class TestDetectionMeanings:
    def test_step_answers_are_per_step(self):
        opts = step_options("no_mac_observed", "dr_power")
        assert set(opts) == {"yes", "no"}
        assert "maitinim" in opts["no"].lower()  # per-STEP wording, not the generic gloss

    def test_unknown_fault_or_step_falls_back(self):
        assert step_options("no_such_fault", "dr_power") is None
        assert step_options("no_mac_observed", "no_such_step") is None
        assert step_options(None, None) is None


class TestProcedure:
    def test_unclear_fault_is_a_single_escalate_pack(self):
        strat = get_strategy("unclear_fault")
        assert [s.role for s in strat.steps] == ["escalate"]
        assert strat.rag_doc is None

    def test_get_strategy_serves_the_pack(self):
        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed", "router_hung"):
            assert get_strategy(verdict) is build_strategy(verdict), verdict

    def test_unknown_verdict_has_no_strategy(self):
        assert get_strategy("no_such_verdict") is None
        assert get_strategy(None) is None
