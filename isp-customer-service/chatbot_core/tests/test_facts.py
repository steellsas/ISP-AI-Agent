"""Wave 3: the telemetry reading, as facts.

The old decision tree (`verdict.py::decide`) turned one signal dict into one verdict, and
everything it knew about the line lived in those branches. These tests hold the new
reading to the same information: for every situation the tree could recognise, the facts
must say what the tree used to conclude — WITHOUT concluding it (the cards do that).

Table-driven on purpose (P-9): a new signal is a new row, not a new test.
"""

import pytest
from agent.facts import facts_from_signals

# A healthy line with the router hung: the provider side is fine, the device is on the
# line and asking nothing, and no traffic flows.
BASE = {
    "billing_suspended": False,
    "incident": None,
    "switch_status": "active",
    "port_link": "up",
    "observed_mac": "aa:bb:cc:dd:ee:ff",
    "registered_mac": "aa:bb:cc:dd:ee:ff",
    "crc_error_rate": 0.1,
    "dhcp_status": "ok",
    "traffic": "none",
    "port_flap_recent": False,
    "neighbors_up": None,
    "neighbors_down": None,
}

# (the situation the old tree called this, the signals that differ, the facts that must
#  follow — only the ones the situation turns on)
CASES = [
    ("router_hung", {}, {"traffic": "none", "line_link": "up", "dhcp": "ok"}),
    ("billing_suspended", {"billing_suspended": True}, {"service_suspended": "yes"}),
    ("active_outage", {"incident": {"outage_id": "O1"}}, {"area_outage": "yes"}),
    (
        "switch_unreachable",
        {"switch_status": "down"},
        {"node_reachable": "no"},
    ),
    (
        "node_fault_unregistered",
        {"port_link": "down", "neighbors_up": 0, "neighbors_down": 4},
        {"line_link": "down", "neighbours": "all_down"},
    ),
    (
        "link_down_local",
        {"port_link": "down", "neighbors_up": 6, "neighbors_down": 1},
        {"line_link": "down", "neighbours": "mixed"},
    ),
    ("no_mac_observed", {"observed_mac": None}, {"device_seen": "no"}),
    (
        "foreign_mac",
        {"observed_mac": "11:22:33:44:55:66"},
        {"device_seen": "yes", "device_registered": "foreign"},
    ),
    ("crc_errors", {"crc_error_rate": 12.0}, {"line_errors": "high"}),
    ("dhcp_silent", {"dhcp_status": "no_requests"}, {"dhcp": "silent"}),
    ("dhcp_silent_expired", {"dhcp_status": "expired"}, {"dhcp": "silent"}),
    ("healthy_to_router", {"traffic": "flowing"}, {"traffic": "flowing"}),
    (
        "after_a_real_reboot",
        {"traffic": "flowing", "port_flap_recent": True},
        {"traffic": "flowing", "port_flapped": "yes"},
    ),
]


@pytest.mark.parametrize("situation, signals, expected", CASES)
def test_the_signals_become_the_facts_the_tree_used(situation, signals, expected):
    facts = facts_from_signals({**BASE, **signals})
    assert {k: facts.get(k) for k in expected} == expected, situation


def test_nothing_seen_is_not_the_same_as_nothing_wrong():
    """The reading failed (no port data): every line fact is `unknown`, never a clean
    value. A card that requires `line_link=up` must not match a line we never saw."""
    facts = facts_from_signals(dict.fromkeys(BASE))

    assert facts["line_link"] == "unknown"
    assert facts["node_reachable"] == "unknown"
    assert facts["dhcp"] == "unknown"
    assert facts["traffic"] == "unknown"
    assert facts["device_registered"] == "unknown"


def test_a_device_we_cannot_compare_is_unknown_not_foreign():
    """A missing registration is not evidence of a swapped router — that difference is a
    whole fault card (`foreign_mac`), so it may never be guessed."""
    facts = facts_from_signals({**BASE, "registered_mac": None})

    assert facts["device_seen"] == "yes"
    assert facts["device_registered"] == "unknown"


def test_no_telemetry_at_all_yields_no_facts():
    assert facts_from_signals(None) == {}
    assert facts_from_signals({}) == {}


def test_every_fact_the_catalogue_declares_is_readable():
    """Each entry in signals.yaml must produce a value for a full reading — a fact nobody
    can read is a card condition that can never be met."""
    from agent.contract import signals as catalog

    facts = facts_from_signals(BASE)
    assert set(facts) == set(catalog.get())
