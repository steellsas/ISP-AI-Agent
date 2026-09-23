"""diagnose_connection — the provider-side READING, end to end.

The verdict tree that used to live in `agent/verdict.py` is gone (wave 4): the reading returns
signals, the signals become facts, and the CARDS decide which fault those facts allow. So this
file walks the whole new chain on the seeded demo customers:

    the demo database -> gather_signals -> facts -> the card the facts leave standing

which is a stronger statement than the old one (the tree's envelope) — it proves the reading,
the fact mapping and the cards agree about every scenario the demo ships.
"""

import pytest
from agent.case import candidates, fallback
from agent.facts import facts_from_signals


def _matched(customer_id: str) -> set[str]:
    """The faults the line's own reading leaves standing for this customer."""
    from agent.tools import diagnose_connection

    result = diagnose_connection(customer_id)
    assert result["success"] is True, result
    facts = facts_from_signals(result["signals"])
    return {c.fault for c in candidates(facts) if c.status == "matched"}


# (the seeded customer, what the line says about them)
SEEDED = [
    ("CUST101", "billing_suspended"),  # S1: the service is suspended for a debt
    ("CUST102", "active_outage"),  # S2: a registered outage in their area
    ("CUST103", "switch_unreachable"),  # S3: our own node is unreachable
    ("CUST104", "link_down_local"),  # S4: their link is down, the neighbours are up
    ("CUST105", "foreign_mac"),  # S5a: a different device on the line
    ("CUST112", "router_hung"),  # S6: the device is there and silent
]


@pytest.mark.parametrize("customer_id, fault", SEEDED)
def test_the_reading_leaves_the_right_card_standing(customer_id, fault, db_connection):
    assert _matched(customer_id) == {fault}, customer_id


def test_a_silent_router_is_read_as_its_own_fault(db_connection):
    """CUST106 — a factory-reset router: the line carries traffic and the device asks for no
    address at all. The card that owns that reading is `dhcp_silent`, and it is the whole of
    what the deleted tree knew about this line (wave 4a regression, eval X)."""
    from agent.facts import facts_from_signals
    from agent.tools import diagnose_connection

    facts = facts_from_signals(diagnose_connection("CUST106")["signals"])
    assert facts["dhcp"] == "silent" and facts["traffic"] == "flowing"
    assert _matched("CUST106") == {"dhcp_silent"}


def test_the_client_side_card_needs_the_device_to_be_talking(db_connection):
    """A silent device is not a client-side problem: the caller is not walked through their
    own laptop while the router has no configuration."""
    assert "healthy_to_router" not in _matched("CUST106")


def test_the_honest_ending_is_there_for_what_nothing_describes(db_connection):
    assert fallback().fault == "unclear_fault"


def test_a_reading_that_fails_says_so(db_connection):
    from agent.tools import diagnose_connection

    result = diagnose_connection("NOPE")
    assert result["success"] is False and result.get("error")
