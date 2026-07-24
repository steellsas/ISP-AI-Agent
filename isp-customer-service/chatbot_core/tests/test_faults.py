"""
Tests for the declarative fault definitions (Phase 3.8 step 5b).

The manifest is the knowledge layer a new fault is written in; these guard that it stays
loadable, fail-soft, and IN SYNC with the strategies in code — a silent drift there would
send the classifier the wrong meanings.
"""

from agent.faults import playbook, purpose_triggers, step_options
from agent.resolution import STRATEGIES


class TestLoader:
    def test_step_options_are_per_step_meanings(self):
        opts = step_options("no_mac_observed", "dr_power")
        assert set(opts) == {"yes", "no"}
        # per-STEP wording, more precise than the generic "lights" gloss
        assert "maitinim" in opts["no"].lower()

    def test_unknown_fault_or_step_falls_back(self):
        assert step_options("no_such_fault", "dr_power") is None
        assert step_options("no_mac_observed", "no_such_step") is None
        assert step_options(None, None) is None

    def test_playbook_and_triggers_present(self):
        assert playbook("no_mac_observed")
        trig = purpose_triggers()
        assert trig and all(isinstance(v, list) and v for v in trig.values())


class TestManifestMatchesCode:
    """The manifest must describe the real strategies — otherwise the classifier gets
    meanings for steps that no longer exist (or misses ones that do)."""

    def test_playbook_matches_strategy_rag_doc(self):
        for verdict, strat in STRATEGIES.items():
            declared = playbook(verdict)
            if declared:  # a fault may not be in the manifest yet
                assert declared == strat.rag_doc, verdict

    def test_every_declared_step_exists_in_its_strategy(self):
        for verdict, strat in STRATEGIES.items():
            ids = {s.id for s in strat.steps}
            for step_id in _declared_steps(verdict) or {}:
                assert step_id in ids, f"{verdict}: unknown step {step_id}"

    def test_declared_keys_match_the_step_routing_keys(self):
        # Some steps key `on` by the Outcome enum, so compare against the routing VALUE
        # ("yes"), not str(Outcome.YES) — the same normalisation the classifier uses.
        for verdict, strat in STRATEGIES.items():
            for step in strat.steps:
                opts = step_options(verdict, step.id)
                if opts:
                    keys = {str(getattr(k, "value", k)) for k in step.on}
                    assert set(opts) == keys, f"{verdict}.{step.id}"


def _declared_steps(verdict: str):
    from agent.faults import _load

    return (_load().get(verdict) or {}).get("steps")
