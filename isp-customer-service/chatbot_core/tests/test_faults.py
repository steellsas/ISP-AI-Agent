"""
Tests for the declarative fault knowledge (Phase 3.8 step 5b/5c).

`knowledge/faults.yaml` is now the source for the call's PURPOSE (triggers), the
PROCEDURE (steps) and the DETECTION meanings (answers). These guard that it stays
loadable, fail-soft, and EQUIVALENT to the in-code registry it replaces — a silent drift
would change how the agent routes without anyone noticing.
"""

from agent.faults import build_strategy, classify_purpose, playbook, step_options
from agent.resolution import STRATEGIES, get_strategy


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


class TestDetectionMeanings:
    def test_step_answers_are_per_step(self):
        opts = step_options("no_mac_observed", "dr_power")
        assert set(opts) == {"yes", "no"}
        assert "maitinim" in opts["no"].lower()  # per-STEP wording, not the generic gloss

    def test_unknown_fault_or_step_falls_back(self):
        assert step_options("no_such_fault", "dr_power") is None
        assert step_options("no_mac_observed", "no_such_step") is None
        assert step_options(None, None) is None


class TestProcedureEquivalence:
    """The manifest must rebuild EXACTLY the strategies the walker used to get from code."""

    def test_every_code_strategy_is_declared(self):
        for verdict in STRATEGIES:
            assert build_strategy(verdict) is not None, verdict
            assert playbook(verdict) == STRATEGIES[verdict].rag_doc, verdict

    def test_declared_steps_match_code_steps(self):
        for verdict, coded in STRATEGIES.items():
            declared = build_strategy(verdict)
            assert [s.id for s in declared.steps] == [s.id for s in coded.steps], verdict
            for d, c in zip(declared.steps, coded.steps):
                assert d.kind == c.kind, f"{verdict}.{d.id} kind"
                assert d.detector == c.detector, f"{verdict}.{d.id} detector"
                assert d.rag_section == c.rag_section, f"{verdict}.{d.id} rag_section"
                assert d.goto == c.goto, f"{verdict}.{d.id} goto"
                assert d.tools == c.tools, f"{verdict}.{d.id} tools"
                assert d.tool_actions == c.tool_actions, f"{verdict}.{d.id} tool_actions"
                # `on` keys may be Outcome members in code — compare routing VALUES
                coded_on = {str(getattr(k, "value", k)): v for k, v in c.on.items()}
                assert d.on == coded_on, f"{verdict}.{d.id} on"

    def test_get_strategy_serves_the_declared_one(self):
        for verdict in STRATEGIES:
            assert get_strategy(verdict) is build_strategy(verdict), verdict

    def test_unknown_verdict_has_no_strategy(self):
        assert get_strategy("no_such_verdict") is None
        assert get_strategy(None) is None
