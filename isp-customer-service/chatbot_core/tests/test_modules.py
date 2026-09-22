"""Wave 3d: one module call becomes one turn.

The same call — `reboot(device=router)` — must work for a TP-Link, for a box we have never
seen, and (in wave 4) for a TV decoder. What changes is the wording, and that comes from the
equipment catalogue, not from the card.
"""

import pytest
from agent.contract.schema import ModuleCall
from agent.ledger import facts_of, record_client, record_telemetry, record_unavailable, unavailable
from agent.modules import can_offer, plan_step, step_done

from tests.test_facts import BASE


def _call(module, **args):
    return ModuleCall(module=module, args=args)


class TestAModuleBecomesATurn:
    def test_an_instruction_is_worded_for_the_caller_s_device(self):
        tplink = plan_step(
            _call("reboot", device="router", method="button"), model="TP-Link Archer C6"
        )
        assert tplink.kind == "instruct"
        assert "mygtukas" in tplink.text  # the family's own wording

    def test_an_unknown_device_gets_the_basic_wording(self):
        unknown = plan_step(_call("reboot", device="router"), model="Huawei HG8245")
        assert "maitinimo laidą" in unknown.text

    def test_what_the_catalogue_cannot_word_is_not_offered(self):
        """No basic router file describes a button, so the engine must not improvise where
        one is — `can_offer` is how the solution skips it."""
        button = _call("reboot", device="router", method="button")
        assert can_offer(button, model="TP-Link Archer C6")
        assert not can_offer(button, model="Huawei HG8245")

    def test_a_question_says_which_fact_it_waits_for(self):
        lights = plan_step(_call("check_lights", device="router", light="internet"))
        assert lights.kind == "ask" and lights.awaits == "wan_link"
        assert "lemputė" in lights.text

    def test_an_engine_action_names_its_tool_and_asks_nothing(self):
        bind = plan_step(_call("bind", device="router"))
        assert bind.kind == "action" and bind.tool == "update_mac" and bind.awaits is None

    def test_a_verification_carries_the_probe_and_the_evidence(self):
        verify = plan_step(
            _call("verify", evidence=["traffic=flowing", "port_flapped=yes"], ask="restored")
        )
        assert verify.kind == "verify" and verify.tool == "diagnose_connection"
        assert verify.evidence == ("traffic=flowing", "port_flapped=yes")

    def test_an_escalation_carries_what_the_ticket_must_say(self):
        out = plan_step(_call("escalate", note="perkrauta, neatsistatė"))
        assert out.kind == "escalate" and out.note == "perkrauta, neatsistatė"

    def test_the_goal_names_the_device(self):
        assert "router" in plan_step(_call("reach", device="router")).goal


class TestWhenAStepIsDone:
    def test_the_evidence_settles_it(self):
        call = _call("verify", evidence=["traffic=flowing", "port_flapped=yes"])
        assert step_done(call, {"traffic": "flowing", "port_flapped": "yes"}) is True

    def test_a_reboot_nobody_saw_did_not_happen(self):
        """Traffic came back but the device never dropped off the line: something else was
        power-cycled, and the card's retry says so kindly."""
        call = _call("verify", evidence=["traffic=flowing", "port_flapped=yes"])
        assert step_done(call, {"traffic": "flowing", "port_flapped": "no"}) is False

    def test_while_the_probe_has_not_answered_it_is_neither(self):
        call = _call("verify", evidence=["traffic=flowing"])
        assert step_done(call, {}) is None

    def test_a_step_with_only_the_caller_s_word_is_settled_by_the_engine(self):
        assert step_done(_call("verify", ask="restored"), {"traffic": "flowing"}) is None


class TestTheLedger:
    def test_telemetry_lands_as_facts_and_says_what_changed(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        changed = record_telemetry(state, rt, BASE)
        assert changed["traffic"] == "none"
        assert facts_of(state)["line_link"] == "up"

        again = record_telemetry(state, rt, {**BASE, "traffic": "flowing"})
        assert again == {"traffic": "flowing"}  # only the difference

    def test_the_caller_cannot_overwrite_the_line(self, make_state, make_runtime):
        """D-07: telemetry is the arbiter. "But it works!" does not make traffic flow."""
        state, rt = make_state("+37060020112"), make_runtime()
        state.diagnosis.verdicts["network"] = {"signals": BASE}
        record_telemetry(state, rt, BASE)

        assert record_client(state, rt, "traffic", "flowing") is False
        assert facts_of(state)["traffic"] == "none"

    def test_what_only_the_caller_knows_is_written(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        assert record_client(state, rt, "fail_scope", "all") is True
        assert facts_of(state)["fail_scope"] == "all"

    def test_a_dead_end_is_remembered_and_then_forgotten_when_it_answers(
        self, make_state, make_runtime
    ):
        state, rt = make_state("+37060020112"), make_runtime()
        record_unavailable(state, rt, "fail_scope")
        assert unavailable(state) == frozenset({"fail_scope"})

        record_client(state, rt, "fail_scope", "one")
        assert unavailable(state) == frozenset()

    def test_a_probe_that_answers_clears_its_own_dead_end(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        record_unavailable(state, rt, "traffic")
        record_telemetry(state, rt, BASE)
        assert unavailable(state) == frozenset()


@pytest.mark.parametrize(
    "module",
    [
        "reach",
        "reboot",
        "check_lights",
        "cable",
        "device_check",
        "connect_direct",
        "bind",
        "verify",
        "escalate",
    ],
)
def test_every_module_can_be_planned(module):
    """A module nobody can plan is a card that would stall mid-solution."""
    args = {"device": "router"}
    if module == "verify":
        args = {"evidence": ["traffic=flowing"]}
    if module == "connect_direct":
        args = {"to": "computer"}
    if module == "escalate":
        args = {"note": "x"}
    assert plan_step(ModuleCall(module=module, args=args)) is not None
