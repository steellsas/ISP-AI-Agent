"""
S6 „pakibęs routeris" (2026-08-31) — pirmoji gedimo kortelė, užpildyta pagal
AGENT_ONBOARDING.md D klausimyną (Andrius = užsakovo technikas).

Layers:
- verdict: device visible + DHCP ok + traffic 'none' -> router_hung (after the
  dhcp/crc checks, before healthy_to_router); _flap_recent = the reboot witness.
- card: knowledge/v2/cards/router_hung.yaml (the v1 pack and its walker are gone).
- sim: simulate_router_reboot on the seeded CUST112 (traffic returns + the
  port flap the witness reads).
"""

from datetime import UTC

from agent.verdict import _flap_recent


def _signals(**overrides) -> dict:
    base = {
        "customer_id": "CUST_TEST",
        "billing_suspended": False,
        "suspension_reason": None,
        "incident": None,
        "switch_status": "active",
        "port_link": "up",
        "registered_mac": "00:1A:2B:3C:4D:01",
        "observed_mac": "00:1A:2B:3C:4D:01",
        "crc_error_rate": 0.0,
        "dhcp_status": "ok",
        "traffic": "normal",
        "port_flap_recent": False,
        "neighbors_up": 5,
        "neighbors_down": 0,
    }
    base.update(overrides)
    return base


def _hung_payload(reason="router_hung", flap=False):
    return {
        "success": True,
        "verdict": {"reason": reason, "side": "customer", "group": "B6"},
        "signals": {"traffic": "none", "port_flap_recent": flap},
    }


class TestRebootCheckDetector:
    """Dedicated rh_check vocabulary — negation wins, 'dega' alone unclear.
    (Live 2026-08-31: generic restored read 'jos nemirksi' as YES via the
    'jo' substring and closed an unresolved call.)"""

    def test_live_phrases(self):
        from agent.perceive.detectors import detect_reboot_check as d
        from agent.resolution import Outcome

        assert d("Visos lemputės dega, bet jos nemirksi") is Outcome.NO
        assert d("Pabandžiau, nėra interneto") is Outcome.NO
        assert d("Nemirksi lemputė") is Outcome.NO
        assert d("Mirksi, puslapis atsidaro — veikia") is Outcome.YES
        assert d("Taip, mirksi ir atsidaro") is Outcome.YES

    def test_unclear_stays_unclear(self):
        from agent.perceive.detectors import detect_reboot_check as d

        assert d("Dega lemputės") is None  # burning != working
        assert d("Ned.") is None
        assert d("Palaukite, dar žiūriu") is None
        assert d("") is None


class TestConflictScope:
    """Undeclared-key conflicts settle silently (S6 live: 'lights' chatter
    hijacked two turns of the hung-router flow with a clarify loop)."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060020112")
        agent.state.identity.customer_id = "CUST112"
        agent.state.intake.problem_type = "internet_down"
        return agent

    def test_undeclared_key_conflict_settles_silently(self, db_connection):
        """`device_present` is declared by no card: chatter about it must not hijack the
        flow with a clarify loop. (The conflict scope is every card's needs since v1's
        `resolution.procedure` went — it used to narrow to the walker's one pack, and this
        test used `outlet_works`, which the dead-router card declares.)"""
        from agent.evidence import CLIENT, set_fact
        from agent.perceive.evidence import _conflict_to_clarify

        agent = self._agent()
        set_fact(agent.state.diagnosis.evidence, "device_present", "found", CLIENT, 1)
        entry = set_fact(agent.state.diagnosis.evidence, "device_present", "missing", CLIENT, 2)
        assert entry["conflict"]
        assert (
            _conflict_to_clarify(agent.state, agent.runtime, "device_present", entry) is True
        )  # consumed silently
        assert agent.state.diagnosis.contradiction is None  # no clarify loop
        assert entry["value"] == "missing" and not entry["conflict"]  # newest stands

    def test_declared_key_conflict_still_clarifies(self, db_connection):
        from agent.evidence import CLIENT, set_fact
        from agent.perceive.evidence import _conflict_to_clarify

        agent = self._agent()
        set_fact(agent.state.diagnosis.evidence, "lights", "off", CLIENT, 1)
        entry = set_fact(agent.state.diagnosis.evidence, "lights", "on", CLIENT, 2)
        assert entry["conflict"]
        assert _conflict_to_clarify(agent.state, agent.runtime, "lights", entry) is True
        c = agent.state.diagnosis.contradiction
        assert (c.fact_key, c.before_value, c.now_value) == ("lights", "off", "on")


class TestSimRebootSeed:
    """Seeded CUST112 + the demo reboot button, end to end (and restored)."""

    def _card_and_signals(self):
        """What the line says, and which card the facts leave standing (wave 4: the reading
        returns signals; the cards decide)."""
        import json

        from agent.case import candidates
        from agent.facts import facts_from_signals
        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST112"}))
        signals = d.get("signals") or {}
        matched = {
            c.fault for c in candidates(facts_from_signals(signals)) if c.status == "matched"
        }
        return matched, signals

    def _restore_hung(self, db):
        with db.transaction() as cur:
            cur.execute(
                "UPDATE ports SET traffic_status='none', "
                "last_status_change=datetime('now','-2 days') WHERE customer_id='CUST112'"
            )

    def test_seeded_hung_then_reboot_restores(self, db_connection):
        from agent.tools import simulate_router_reboot

        try:
            matched, signals = self._card_and_signals()
            assert matched == {"router_hung"}
            assert signals.get("port_flap_recent") is False
            res = simulate_router_reboot("CUST112")
            assert res["success"] is True
            matched, signals = self._card_and_signals()
            assert matched == {"healthy_to_router"}  # traffic is back; the rest is client-side
            assert signals.get("traffic") == "normal"
            assert signals.get("port_flap_recent") is True  # the witness
        finally:
            self._restore_hung(db_connection)
