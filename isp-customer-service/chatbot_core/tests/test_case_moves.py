"""Wave 3c: what the Case does next.

The engine used to hold one verdict and a walker pointing at a step, with handover rules
between three drivers (review finding N). Now there is one question — given the facts,
what now — and one answer: learn a fact, run a solution, or end honestly.

The tests are a table of positions, not conversations: the same facts must always produce
the same move, or a call is not reproducible.
"""

import pytest
from agent.case import Move, next_move, sources_for
from agent.facts import facts_from_signals

from tests.test_facts import BASE


def _facts(**signals) -> dict[str, str]:
    return facts_from_signals({**BASE, **signals})


class TestLookBeforeAsking:
    """The caller's patience is the scarcest thing in the call."""

    def test_with_nothing_known_the_engine_looks_at_the_line(self):
        move = next_move({})
        assert move.kind == "learn" and move.source.kind == "probe"
        assert move.source.tool == "diagnose_connection"

    def test_a_fact_only_the_caller_knows_is_asked(self):
        """Telemetry cannot see how many devices fail at home."""
        move = next_move(_facts())
        assert move.kind == "learn" and move.fact == "fail_scope"
        assert move.source.kind == "ask"
        assert move.source.ask == "pack.router_hung.fail_scope.question"

    def test_a_fact_a_module_can_get_beats_a_question(self):
        """`wan_link` comes from looking at the lights together, not from an opinion."""
        assert [s.kind for s in sources_for("wan_link")] == ["module"]
        assert sources_for("wan_link")[0].module == "check_lights"

    def test_telemetry_wins_over_a_module_for_the_same_fact(self):
        kinds = [s.kind for s in sources_for("traffic")]
        assert kinds[0] == "probe"


class TestTheFaultDecidesTheFix:
    def test_a_settled_fault_runs_its_own_steps(self):
        move = next_move({**_facts(), "fail_scope": "all"})
        assert move.kind == "solve" and move.fault == "router_hung"
        assert [s.module for s in move.steps] == ["reach", "reboot", "verify"]

    def test_the_other_branch_hands_the_case_to_another_card(self):
        """ "Only one device" is not a hung router — the client-side card takes over, and
        its own first question follows."""
        move = next_move({**_facts(), "fail_scope": "one"})
        assert move.kind == "learn" and move.fault == "healthy_to_router"
        assert move.fact in ("fail_device", "rebooted", "connection_type")

    def test_a_fault_with_nothing_left_to_ask_goes_straight_to_its_fix(self):
        move = next_move(_facts(crc_error_rate=12.0))
        assert move.kind == "solve" and move.fault == "crc_errors"
        assert [s.module for s in move.steps] == ["reach", "cable", "verify"]

    def test_the_foreign_device_asks_the_one_thing_that_changes_the_fix(self):
        move = next_move(_facts(observed_mac="11:22:33:44:55:66"))
        assert move.kind == "learn" and move.fact == "changed_device"


class TestWhenNothingFits:
    def test_news_is_told_not_diagnosed(self):
        """A suspended service is NEWS: the engine says it and the caller is asked to do
        nothing (wave 4 — it used to be a branch in the tree)."""
        move = next_move(_facts(billing_suspended=True))
        assert move.kind == "inform" and move.fault == "billing_suspended"

    def test_a_fault_no_card_describes_ends_honestly(self):
        """No card claims a line whose port data is missing entirely — the honest ending,
        not the closest-looking procedure."""
        move = next_move({"line_link": "unknown", "node_reachable": "no", "neighbours": "mixed"})
        assert move.kind in ("escalate", "inform")

    def test_a_silent_router_is_solved_by_its_own_card(self):
        """What the tree used to call `dhcp_silent` is a card, and its card says there is
        nothing to do over the phone (wave 4a regression, eval X)."""
        move = next_move(_facts(dhcp_status="no_requests"))
        assert move.kind == "solve" and move.fault == "dhcp_silent"
        assert [call.module for call in move.steps] == ["escalate"]

    def test_a_fact_we_could_not_get_is_not_asked_again(self):
        """The caller could not answer; the engine moves on instead of looping."""
        facts = _facts()
        first = next_move(facts)
        again = next_move(facts, unavailable=frozenset({first.fact}))
        assert again.fact != first.fact

    def test_a_fault_whose_branches_all_need_an_answer_we_cannot_get_ends_honestly(self):
        facts = {**_facts(), "fail_scope": "one"}
        blocked = frozenset({"fail_device", "connection_type", "rebooted", "fail_scope"})
        move = next_move(facts, unavailable=blocked)
        assert move.kind == "escalate"


class TestTheMoveIsReproducible:
    @pytest.mark.parametrize(
        "facts",
        [{}, {"traffic": "none"}, {"line_link": "up", "device_seen": "yes"}],
    )
    def test_the_same_facts_give_the_same_move(self, facts):
        assert next_move(dict(facts)) == next_move(dict(facts))

    def test_a_move_says_why(self):
        move = next_move({})
        assert isinstance(move, Move) and move.why
