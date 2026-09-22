"""Wave 3: the facts decide which faults are still possible.

This is the test that says the cards reproduce what the old decision tree knew. The tree
turned a signal dict into ONE verdict; the cards must reach the same fault from the same
signals — and, unlike the tree, they must also be able to hold several candidates while a
question is still open.
"""

import pytest
from agent.case import candidates, fallback, judge, open_candidates
from agent.contract import cards as catalog
from agent.facts import facts_from_signals

from tests.test_facts import BASE


def _facts(**signals):
    return facts_from_signals({**BASE, **signals})


def _matched(facts):
    return {c.fault for c in candidates(facts) if c.status == "matched"}


# (what the old tree concluded, the signals, the card that must match)
TREE = [
    ("router_hung", {}, "router_hung"),
    ("healthy_to_router", {"traffic": "flowing"}, "healthy_to_router"),
    ("foreign_mac", {"observed_mac": "11:22:33:44:55:66"}, "foreign_mac"),
    ("crc_errors", {"crc_error_rate": 12.0}, "crc_errors"),
    ("no_mac_observed", {"observed_mac": None}, "no_mac_observed"),
    (
        "link_down_local",
        {"port_link": "down", "neighbors_up": 6, "neighbors_down": 1},
        "link_down_local",
    ),
]


@pytest.mark.parametrize("verdict, signals, card", TREE)
def test_the_cards_reach_the_verdict_the_tree_reached(verdict, signals, card):
    """One card matches, and it is the one the tree named."""
    assert _matched(_facts(**signals)) == {card}, verdict


class TestWhatIsNotACard:
    """The tree also produced verdicts that no card ever described. Those must fall to the
    honest fallback, not to whichever card looks closest."""

    @pytest.mark.parametrize(
        "situation, signals",
        [
            ("billing_suspended", {"billing_suspended": True}),
            ("active_outage", {"incident": {"outage_id": "O1"}}),
            ("switch_unreachable", {"switch_status": "down"}),
            (
                "node_fault_unregistered",
                {"port_link": "down", "neighbors_up": 0, "neighbors_down": 4},
            ),
            ("dhcp_silent", {"dhcp_status": "no_requests"}),
        ],
    )
    def test_no_card_claims_it(self, situation, signals):
        assert _matched(_facts(**signals)) == set(), situation

    def test_the_fallback_is_there_for_them(self):
        assert fallback().fault == "unclear_fault"


class TestSeveralCandidatesAtOnce:
    """What the single verdict could never do (review finding P)."""

    def test_an_unasked_question_keeps_a_card_alive(self):
        """With no telemetry at all, nothing is ruled out and nothing is settled — every
        card is still possible, which is exactly the state a call starts in."""
        judged = open_candidates({})
        assert {c.status for c in judged} == {"possible"}
        assert len(judged) == len(catalog.cards()) - 1  # minus the fallback

    def test_one_fact_can_close_several_cards_at_once(self):
        facts = _facts(observed_mac="11:22:33:44:55:66")  # a foreign device on the line
        ruled_out = {c.fault for c in candidates(facts) if c.status == "ruled_out"}
        assert "router_hung" in ruled_out and "no_mac_observed" in ruled_out

    def test_a_card_says_what_it_is_still_waiting_for(self):
        """The unknown conditions ARE the next question — the engine does not guess."""
        card = catalog.card("link_down_local")
        verdict = judge(card, {"node_reachable": "yes", "line_link": "down"})
        assert verdict.status == "possible"
        assert verdict.unknown == ("neighbours=mixed",)
        assert verdict.why == ("node_reachable=yes", "line_link=down")

    def test_a_ruled_out_card_says_what_killed_it(self):
        card = catalog.card("router_hung")
        verdict = judge(card, _facts(crc_error_rate=12.0))
        assert verdict.status == "ruled_out"
        assert verdict.against == ("line_errors=high",)
