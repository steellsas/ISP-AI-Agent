"""Unit tests for the resolution strategy sequencer (agent/resolution.py).

Pure logic — no LLM, no DB. Proves the engine walks a strategy deterministically:
the model cannot skip, and each outcome routes to the right next step / terminal.
"""

from agent.resolution import (
    STRATEGIES,
    TERMINALS,
    Outcome,
    StepKind,
    detect_yes_no,
    get_strategy,
    next_step_id,
)


class TestDetectYesNo:
    def test_clear_yes(self):
        assert detect_yes_no("taip, prijungiau naują routerį") == Outcome.YES
        assert detect_yes_no("aha, pakeičiau") == Outcome.YES

    def test_denial_wins(self):
        assert detect_yes_no("nieko nekeičiau, nieko nedariau") == Outcome.NO
        assert detect_yes_no("ne") == Outcome.NO
        assert detect_yes_no("routerio nekeičiau") == Outcome.NO

    def test_unclear_is_none(self):
        assert detect_yes_no("nežinau tiksliai kas ten") == Outcome.NO  # nežinau -> denial
        assert detect_yes_no("gerai") is None
        assert detect_yes_no("") is None
        assert detect_yes_no(None) is None


class TestRegistry:
    def test_known_verdict_returns_strategy(self):
        s = get_strategy("foreign_mac")
        assert s is not None and s.verdict == "foreign_mac"
        assert s.rag_doc  # every strategy points at a playbook

    def test_unknown_verdict_is_none(self):
        assert get_strategy("healthy_to_router") is None
        assert get_strategy(None) is None

    def test_steps_are_ordered_and_unique(self):
        s = get_strategy("foreign_mac")
        ids = [st.id for st in s.steps]
        assert ids == ["confirm_change", "bind_mac", "verify", "escalate"]
        assert len(ids) == len(set(ids))

    def test_action_tools_are_step_scoped(self):
        s = get_strategy("foreign_mac")
        # binding is only exposed on bind_mac; registering only on escalate.
        assert s.step("confirm_change").tools == frozenset()  # no action during confirm
        assert "update_mac" in s.step("bind_mac").tools
        assert "create_ticket" in s.step("escalate").tools


class TestForeignMacSequence:
    def setup_method(self):
        self.s = STRATEGIES["foreign_mac"]

    def test_confirm_yes_falls_through_to_action(self):
        # No explicit route for YES -> next step in order.
        assert next_step_id(self.s, "confirm_change", Outcome.YES) == "bind_mac"

    def test_confirm_no_escalates(self):
        assert next_step_id(self.s, "confirm_change", Outcome.NO) == "escalate"

    def test_action_falls_through_to_verify(self):
        assert next_step_id(self.s, "bind_mac", None) == "verify"

    def test_verify_fixed_resolves(self):
        assert next_step_id(self.s, "verify", Outcome.FIXED) == "resolve"

    def test_verify_not_fixed_escalates(self):
        assert next_step_id(self.s, "verify", Outcome.NOT_FIXED) == "escalate"

    def test_happy_path_walks_confirm_action_verify_resolve(self):
        path, cur = [], "confirm_change"
        outcomes = {"confirm_change": Outcome.YES, "bind_mac": None, "verify": Outcome.FIXED}
        for _ in range(10):
            path.append(cur)
            if cur in TERMINALS:
                break
            cur = next_step_id(self.s, cur, outcomes.get(cur))
        assert path == ["confirm_change", "bind_mac", "verify", "resolve"]

    def test_step_kinds_are_typed(self):
        kinds = {st.id: st.kind for st in self.s.steps}
        assert kinds["confirm_change"] == StepKind.CONFIRM
        assert kinds["bind_mac"] == StepKind.ACTION
        assert kinds["verify"] == StepKind.VERIFY

    def test_action_step_declares_backend_tool(self):
        bind = self.s.step("bind_mac")
        assert "update_mac" in bind.tool_actions
