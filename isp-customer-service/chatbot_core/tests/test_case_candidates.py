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


class TestNewsIsACardToo:
    """Wave 4: the provider-side situations the tree used to name are cards now — NEWS cards,
    which say there is nothing to diagnose, only something to tell."""

    @pytest.mark.parametrize(
        "news, signals",
        [
            ("billing_suspended", {"billing_suspended": True}),
            ("active_outage", {"incident": {"outage_id": "O1"}}),
            ("switch_unreachable", {"switch_status": "down"}),
            (
                "node_fault_unregistered",
                {"port_link": "down", "neighbors_up": 0, "neighbors_down": 4},
            ),
        ],
    )
    def test_the_news_card_claims_it(self, news, signals):
        assert news in _matched(_facts(**signals))
        assert catalog.card(news).news is True
        assert not catalog.card(news).solution  # nothing to DO, only to tell

    def test_the_fact_the_tree_knew_and_no_card_did_is_a_card_now(self):
        """`dhcp=silent` — a router that is on the line and does not even ask for an address
        (a factory reset). The tree named it and no card described it, so wave 4a lost the
        situation (eval X); it is a card now, and nothing in code names it."""
        assert _matched(_facts(dhcp_status="no_requests", traffic="none")) == {"dhcp_silent"}
        assert _matched(_facts(dhcp_status="expired")) == {"dhcp_silent"}

    def test_a_silent_device_is_not_the_client_side(self):
        """Traffic can flow on the line while the device asks for nothing: that is the
        router's own configuration, not the caller's laptop, so the client-side card steps
        aside (it used to win on CUST106 and send the caller through Wi-Fi questions)."""
        standing = _matched(_facts(dhcp_status="no_requests", traffic=20))
        assert standing == {"dhcp_silent"} and "healthy_to_router" not in standing

    def test_a_new_device_on_the_line_is_still_the_new_device(self):
        """A router the caller swapped has not asked for an address either — that is part of
        `foreign_mac`, not a second fault (the demo's S1 line shows both facts)."""
        facts = _facts(dhcp_status="no_requests", observed_mac="00:E0:4C:AA:BB:05", traffic=20)
        assert _matched(facts) == {"foreign_mac"}

    def test_the_fallback_is_there_for_them(self):
        assert fallback().fault == "unclear_fault"

    def test_a_card_named_by_a_rule_never_competes_on_facts(self):
        """A service never ordered and a ticket already open come from the CRM profile, not from
        the line, so the facts never make them candidates."""
        for fault in ("service_not_subscribed", "open_ticket_exists"):
            assert catalog.card(fault).set_by == "rule"
            assert fault not in {c.fault for c in candidates(_facts())}


class TestSeveralCandidatesAtOnce:
    """What the single verdict could never do (review finding P)."""

    def test_an_unasked_question_keeps_a_card_alive(self):
        """With no telemetry at all, nothing is ruled out and nothing is settled — every
        card is still possible, which is exactly the state a call starts in."""
        judged = open_candidates({})
        assert {c.status for c in judged} == {"possible"}
        # every card the FACTS can reach: minus the fallback and the two the engine names
        reachable = [c for c in catalog.cards().values() if not c.fallback and c.set_by == "facts"]
        assert len(judged) == len(reachable)

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
