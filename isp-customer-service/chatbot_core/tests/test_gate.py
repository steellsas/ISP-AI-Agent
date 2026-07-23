"""
Unit tests for the solver gate (Phase 3.8 step 3).

The gate is pure 🔒 mechanism (no LLM / IO / state), so it is fully deterministic and
unit-testable — the first new must-hold safety logic of the thinking-agent phase.
"""

from agent.gate import DEFAULT_POLICY, gate
from agent.solver import SolverDecision

KNOWN = {"foreign_mac", "no_mac_observed", "healthy_to_router"}


def _d(action="ask", hyp="no_mac_observed", conf=0.8):
    return SolverDecision(
        current_hypothesis=hyp,
        confidence=conf,
        next_action=action,
        narrator_instruction="…",
    )


class TestAcceptance:
    def test_valid_non_safety_action_accepted(self):
        r = gate(_d("instruct"), known_hypotheses=KNOWN)
        assert r.accepted and r.action == "instruct" and not r.bailout

    def test_mutation_on_mapped_hypothesis_accepted(self):
        r = gate(_d("propose_fix", hyp="foreign_mac"), known_hypotheses=KNOWN)
        assert r.accepted and r.action == "propose_fix"


class TestStructuralValidity:
    def test_no_decision_falls_back_to_ask(self):
        r = gate(None, known_hypotheses=KNOWN)
        assert not r.accepted and r.action == "ask"

    def test_unknown_action_falls_back_to_ask(self):
        r = gate(_d("reboot_everything"), known_hypotheses=KNOWN)
        assert not r.accepted and r.action == "ask"


class TestActionConvergence:
    def test_mutation_on_unmapped_hypothesis_downgraded_to_verify(self):
        # free-text belief the verdict tree does not know -> may NOT bind, only verify
        r = gate(
            _d("propose_fix", hyp="klientas žiūri į ONT, ne routerį"),
            known_hypotheses=KNOWN,
        )
        assert not r.accepted and r.action == "verify"

    def test_non_mutation_on_unmapped_hypothesis_is_fine(self):
        # reasoning freely (ask) about an unknown belief is allowed — only mutation isn't
        r = gate(_d("ask", hyp="klientas žiūri į ONT"), known_hypotheses=KNOWN)
        assert r.accepted and r.action == "ask"


class TestInternalLoopCap:
    def test_internal_action_capped_forces_ask(self):
        cap = DEFAULT_POLICY["internal_hops_max"]
        r = gate(_d("reread_telemetry"), known_hypotheses=KNOWN, internal_hops=cap)
        assert not r.accepted and r.action == "ask"

    def test_internal_action_under_cap_ok(self):
        r = gate(_d("pivot"), known_hypotheses=KNOWN, internal_hops=0)
        assert r.accepted and r.action == "pivot"


class TestBailout:
    def test_low_confidence_streak_bails_to_escalate(self):
        r = gate(
            _d("ask"),
            known_hypotheses=KNOWN,
            low_conf_streak=DEFAULT_POLICY["low_conf_max"],
        )
        assert r.bailout and r.action == "escalate"

    def test_too_many_cycles_bails_to_escalate(self):
        r = gate(
            _d("instruct"),
            known_hypotheses=KNOWN,
            cycles_in_step=DEFAULT_POLICY["cycles_max"] + 1,
        )
        assert r.bailout and r.action == "escalate"

    def test_bailout_wins_over_a_valid_action(self):
        # even a perfectly valid proposal is overridden once we are stuck
        r = gate(
            _d("propose_fix", hyp="foreign_mac"),
            known_hypotheses=KNOWN,
            cycles_in_step=DEFAULT_POLICY["cycles_max"] + 1,
        )
        assert r.bailout and r.action == "escalate"
