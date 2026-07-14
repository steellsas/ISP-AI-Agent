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

    def test_stt_dropped_i_both_directions(self):
        # STT drops the 'i' in BOTH "keičiau"->"kečiau" (yes) and
        # "nekeičiau"->"nekečiau" (no). The denial must still win.
        from agent.resolution import confirms_device_change

        assert detect_yes_no("kečiau routerį") == Outcome.YES
        assert confirms_device_change("kečiau routerį") is True
        assert detect_yes_no("nekečiau") == Outcome.NO
        assert detect_yes_no("nieko nekečiau") == Outcome.NO
        assert confirms_device_change("nekečiau") is False

    def test_unclear_is_none(self):
        assert detect_yes_no("nežinau tiksliai kas ten") == Outcome.NO  # nežinau -> denial
        assert detect_yes_no("gerai") is None
        assert detect_yes_no("") is None
        assert detect_yes_no(None) is None


class TestDetectRestored:
    """confirm_restored uses restoration vocabulary (veikia/atsirado/neveikia),
    NOT the device-change words — 'neveikia' must read as NO despite containing
    'veik'."""

    def test_restored_yes(self):
        from agent.resolution import detect_restored

        assert detect_restored("atsirado internetas") == Outcome.YES
        assert detect_restored("jau veikia") == Outcome.YES
        assert detect_restored("ryšys atsistatė") == Outcome.YES

    def test_restored_no(self):
        from agent.resolution import detect_restored

        assert detect_restored("vis dar neveikia") == Outcome.NO
        assert detect_restored("nevykia") == Outcome.NO  # STT garble
        assert detect_restored("nėra interneto") == Outcome.NO
        assert detect_restored("ne") == Outcome.NO

    def test_restored_unclear(self):
        from agent.resolution import detect_restored

        assert detect_restored("hmm") is None
        assert detect_restored("supratau") is None
        assert detect_restored("") is None


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
        assert ids == [
            "confirm_change",
            "cable_check",
            "cable_reconnect",
            "bind_mac",
            "confirm_restored",
            "client_side",
            "escalate",
        ]
        assert len(ids) == len(set(ids))

    def test_action_tools_are_step_scoped(self):
        s = get_strategy("foreign_mac")
        # binding is only exposed on bind_mac; registering only on escalate.
        assert s.step("confirm_change").tools == frozenset()  # no action during confirm
        assert s.step("cable_check").tools == frozenset()  # instruct, no action
        assert s.step("cable_reconnect").tools == frozenset()  # instruct, no action
        assert s.step("confirm_restored").tools == frozenset()  # asks the caller only
        assert s.step("client_side").tools == frozenset()  # asks the caller only
        assert "update_mac" in s.step("bind_mac").tools
        assert "create_ticket" in s.step("escalate").tools


class TestForeignMacSequence:
    def setup_method(self):
        self.s = STRATEGIES["foreign_mac"]

    def test_confirm_yes_binds_directly(self):
        # Caller changed a device -> bind (skips the cable check).
        assert next_step_id(self.s, "confirm_change", Outcome.YES) == "bind_mac"

    def test_confirm_no_checks_cable(self):
        # Changed nothing -> walk the cable steps, NOT escalate (device is theirs).
        assert next_step_id(self.s, "confirm_change", Outcome.NO) == "cable_check"

    def test_cable_steps_walk_to_bind(self):
        # INSTRUCT steps fall through in order (advanced by the walker on any reply).
        assert next_step_id(self.s, "cable_check", None) == "cable_reconnect"
        assert next_step_id(self.s, "cable_reconnect", None) == "bind_mac"

    def test_action_falls_through_to_confirm_restored(self):
        # After binding we ASK the caller (confirm_restored), not auto-close.
        assert next_step_id(self.s, "bind_mac", None) == "confirm_restored"

    def test_client_side_yes_resolves_no_escalates(self):
        assert next_step_id(self.s, "client_side", Outcome.YES) == "resolve"
        assert next_step_id(self.s, "client_side", Outcome.NO) == "escalate"

    def test_happy_path_changed_device_reaches_confirm_restored(self):
        # confirm_restored is engine-routed (telemetry + caller word), so the static
        # walk stops there — the resolve/pivot/escalate decision lives in the engine.
        path, cur = [], "confirm_change"
        outcomes = {"confirm_change": Outcome.YES, "bind_mac": None}
        for _ in range(10):
            path.append(cur)
            if cur == "confirm_restored" or cur in TERMINALS:
                break
            cur = next_step_id(self.s, cur, outcomes.get(cur))
        assert path == ["confirm_change", "bind_mac", "confirm_restored"]

    def test_nothing_changed_walks_confirm_cable_bind(self):
        path, cur = [], "confirm_change"
        outcomes = {"confirm_change": Outcome.NO}  # cable steps fall through (None)
        for _ in range(10):
            path.append(cur)
            if cur == "confirm_restored" or cur in TERMINALS:
                break
            cur = next_step_id(self.s, cur, outcomes.get(cur))
        assert path == [
            "confirm_change",
            "cable_check",
            "cable_reconnect",
            "bind_mac",
            "confirm_restored",
        ]

    def test_step_kinds_are_typed(self):
        kinds = {st.id: st.kind for st in self.s.steps}
        assert kinds["confirm_change"] == StepKind.CONFIRM
        assert kinds["cable_check"] == StepKind.INSTRUCT
        assert kinds["cable_reconnect"] == StepKind.INSTRUCT
        assert kinds["bind_mac"] == StepKind.ACTION
        assert kinds["confirm_restored"] == StepKind.CONFIRM
        assert kinds["client_side"] == StepKind.CONFIRM

    def test_action_step_declares_backend_tool(self):
        bind = self.s.step("bind_mac")
        assert "update_mac" in bind.tool_actions
