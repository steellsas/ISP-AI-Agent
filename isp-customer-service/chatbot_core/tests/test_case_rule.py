"""Wave 3f: the fault path as the Case drives it, turn by turn.

One driver, one question per turn. These tests walk the S6 call (a hung router) the way the
engine will, asserting the PLAN at each turn — not the wording, which belongs to the
narrator.
"""

import pytest
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry

from tests.test_facts import BASE


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    return state, rt


def said(state, rt, fact, value):
    """A new caller turn: their words land, and the turn counter moves.

    The counter matters — one utterance may move the solution ONE step, because the redecide
    loop re-reads the same words on every hop (live: three steps in one turn, walking past an
    instruction that was never given).
    """
    state.dialog.turn_count += 1
    record_client(state, rt, fact, value)


class TestTheCaseWalksTheCall:
    def test_it_looks_before_it_asks(self, call):
        state, rt = call
        plan = case_rule.plan(state, rt)
        assert plan.rule == "case.probe"
        assert plan.action.type == "tool" and plan.action.name == "diagnose_connection"
        assert plan.redecide_after_action is True  # the same turn decides again
        assert plan.say.kind == "none"  # nothing is said for a check we run ourselves

    def test_with_the_line_read_it_asks_the_one_thing_only_the_caller_knows(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.ask" and plan.awaiting == "fail_scope"
        assert "visuose" in plan.say.text  # the card's own question as the fallback

    def test_the_answer_starts_the_fix(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")

        plan = case_rule.plan(state, rt)

        assert state.case.fault == "router_hung" and state.case.step == 0
        assert plan.rule == "case.reach" and plan.awaiting == "reachable"

    def test_then_one_instruction_per_turn(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach
        said(state, rt, "reachable", "yes")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.reboot" and state.case.step == 1
        assert "maitinimo laidą" in plan.say.text  # the catalogue's words
        assert plan.action.type == "none"  # the caller does this, not the engine

    def test_after_the_reboot_the_engine_verifies_with_the_probe(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)
        said(state, rt, "reachable", "yes")
        case_rule.plan(state, rt)  # reboot
        state.dialog.turn_count += 1
        state.dialog.last_intent = "done"  # "padariau" — the one thing the line cannot say

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.verify"
        assert plan.action.name == "diagnose_connection" and plan.redecide_after_action

    def test_traffic_back_and_a_flap_seen_closes_the_call(self, call):
        state, rt = call
        state.case.facts.update({"fail_scope": "all", "reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        record_telemetry(state, rt, {**BASE, "traffic": "flowing", "port_flap_recent": True})

        plan = case_rule.plan(state, rt)

        assert state.case.step == 3  # past the verification: the fix worked
        assert plan.rule == "case.resolved"
        assert plan.action.type == "close" and plan.action.name == "resolved"


class TestWhenTheFixDoesNotWork:
    def test_a_reboot_nobody_saw_is_retried_once_with_the_card_s_wording(self, call):
        """Traffic came back but the line never saw the device drop: something else was
        power-cycled. The card says retry once — and only once."""
        state, rt = call
        state.case.facts.update({"fail_scope": "all", "reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        record_telemetry(state, rt, {**BASE, "traffic": "none", "port_flap_recent": False})

        plan = case_rule.plan(state, rt)

        assert state.case.step == 1 and plan.rule == "case.reboot"  # back to the reboot
        assert state.case.attempts  # counted, so it cannot loop

    def test_the_second_failure_ends_in_a_technician(self, call):
        state, rt = call
        state.case.facts.update({"fail_scope": "all", "reachable": "yes"})
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 2
        state.case.attempts = {"router_hung.1": 1}
        record_telemetry(state, rt, {**BASE, "traffic": "none"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"


class TestWhenNothingFits:
    def test_an_unreadable_case_ends_honestly(self, call):
        """A fault nothing describes: the honest move is a technician, not the closest-
        looking procedure."""
        state, rt = call
        record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests"})

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate"
        assert state.ticket.stage == "phone"  # the contacts are collected first

    def test_an_outage_or_a_debt_is_not_ours_to_diagnose(self, call):
        """There is nothing to fix — only news to deliver. The Case yields the turn, and
        escalating here hijacked the inform path (full eval: four scenarios)."""
        state, rt = call
        record_telemetry(state, rt, {**BASE, "billing_suspended": True})

        assert case_rule.plan(state, rt) is None
        assert state.ticket.stage is None

    def test_a_step_the_catalogue_cannot_word_is_skipped_not_improvised(self, call):
        """A device nobody described has no button instruction: the engine moves on instead
        of telling the caller to press something that may not exist."""
        from agent.contract.schema import ModuleCall

        state, rt = call
        state.case.fault, state.case.solution, state.case.step = "router_hung", 0, 1
        record_telemetry(state, rt, {**BASE, "device_model": "Huawei HG8245"})
        button = ModuleCall(module="reboot", args={"device": "router", "method": "button"})

        plan = case_rule._module_plan(state, rt, button, state.case.facts, rule="case.reboot")

        assert plan.rule != "case.reboot" or plan.say.text is None


class TestWhenTheCallerCannotDoItNow:
    """P-C: not being at home is a WHEN, not a fault. The caller gets the instruction for
    later and is asked if that suits them — a technician only if they want one."""

    def _at_the_reach_step(self, call):
        state, rt = call
        record_telemetry(state, rt, BASE)
        said(state, rt, "fail_scope", "all")
        case_rule.plan(state, rt)  # reach
        return state, rt

    def test_not_now_gives_the_instruction_for_later(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.homework" and plan.awaiting == "later_agreed"
        assert "Kai būsite namuose" in plan.say.text
        assert "maitinimo laidą" in plan.say.text  # what they were about to be asked to do

    def test_agreeing_closes_the_call_as_a_callback(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")
        case_rule.plan(state, rt)
        said(state, rt, "later_agreed", "yes")

        plan = case_rule.plan(state, rt)

        assert plan.action.type == "close" and plan.action.name == "callback"

    def test_declining_it_offers_a_technician(self, call):
        state, rt = self._at_the_reach_step(call)
        said(state, rt, "reachable", "no")
        case_rule.plan(state, rt)
        said(state, rt, "later_agreed", "no")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.escalate" and state.ticket.stage == "phone"
