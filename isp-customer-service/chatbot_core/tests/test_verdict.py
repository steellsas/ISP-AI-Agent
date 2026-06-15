"""
Tests for the diagnose_connection verdict (agent/verdict.py).

Two layers:
- TestDecide: the pure decision tree over hand-crafted signal dicts —
  every branch of domain doc §3.2 (Steps 1-4, BŪSENA A/B/C).
- TestDiagnoseSeedScenarios: integration over the seeded demo world
  (database/seeds/demo_internet.sql) — each S1-S5 customer must produce
  exactly the verdict the demo plan promises.

Run: pytest tests/test_verdict.py -v
"""

from agent.verdict import decide


def _signals(**overrides) -> dict:
    """A healthy-baseline signals dict; tests override what they probe."""
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
        "neighbors_up": 5,
        "neighbors_down": 0,
    }
    base.update(overrides)
    return base


class TestDecide:
    """Pure decision-tree branches (no DB)."""

    def test_b1_billing_suspended(self):
        v = decide(_signals(billing_suspended=True, suspension_reason="Neapmokėta sąskaita"))
        assert v["group"] == "B1"
        assert v["side"] == "provider"
        assert v["action"] == "inform"
        assert v["reason"] == "billing_suspended"
        assert "Neapmokėta sąskaita" in v["agent_message"]

    def test_b1_wins_over_everything(self):
        """Billing is checked first — even with an outage AND a dead port."""
        v = decide(
            _signals(
                billing_suspended=True,
                incident={"description": "avarija"},
                port_link="down",
            )
        )
        assert v["group"] == "B1"

    def test_b2_active_outage(self):
        v = decide(
            _signals(
                incident={
                    "outage_id": "OUT001",
                    "description": "Perkastas kabelis",
                    "estimated_resolution": "2026-06-11 18:00",
                }
            )
        )
        assert v["group"] == "B2"
        assert v["side"] == "provider"
        assert v["action"] == "inform"
        assert "2026-06-11 18:00" in v["agent_message"]

    def test_b2_wins_over_port_state(self):
        """Registered incident short-circuits port diagnostics (S2 vs S3)."""
        v = decide(_signals(incident={"description": "avarija"}, port_link="down"))
        assert v["group"] == "B2"
        assert v["action"] == "inform"

    def test_b3_switch_unreachable(self):
        v = decide(_signals(switch_status="inactive"))
        assert v["group"] == "B3"
        assert v["side"] == "provider"
        assert v["action"] == "create_ticket"
        assert v["reason"] == "switch_unreachable"

    def test_b3_neighbors_down_unregistered_node_fault(self):
        v = decide(_signals(port_link="down", neighbors_up=0, neighbors_down=4))
        assert v["group"] == "B3"
        assert v["side"] == "provider"
        assert v["action"] == "create_ticket"
        assert v["reason"] == "node_fault_unregistered"

    def test_b4_b5_link_down_neighbors_up(self):
        v = decide(_signals(port_link="down", neighbors_up=5, neighbors_down=1))
        assert v["group"] == "B4/B5"
        assert v["side"] == "customer"
        assert v["action"] == "instruct"
        assert v["reason"] == "link_down_local"

    def test_b6_no_mac_observed(self):
        v = decide(_signals(observed_mac=None))
        assert v["group"] == "B6"
        assert v["side"] == "unclear"
        assert v["action"] == "instruct"
        assert v["reason"] == "no_mac_observed"

    def test_b6_foreign_mac(self):
        v = decide(_signals(observed_mac="00:E0:4C:AA:BB:05"))
        assert v["group"] == "B6"
        assert v["side"] == "customer"
        assert v["reason"] == "foreign_mac"

    def test_mac_compare_case_insensitive(self):
        v = decide(_signals(registered_mac="00:1a:2b:3c:4d:01", observed_mac="00:1A:2B:3C:4D:01"))
        assert v["reason"] != "foreign_mac"

    def test_b5_crc_errors(self):
        v = decide(_signals(crc_error_rate=12.5))
        assert v["group"] == "B5"
        assert v["side"] == "customer"
        assert v["reason"] == "crc_errors"

    def test_b6_dhcp_silent(self):
        v = decide(_signals(dhcp_status="no_requests"))
        assert v["group"] == "B6"
        assert v["side"] == "customer"
        assert v["reason"] == "dhcp_silent"

    def test_b7_healthy_to_router(self):
        v = decide(_signals())
        assert v["group"] == "B7"
        assert v["side"] == "unclear"
        assert v["action"] == "instruct"
        assert v["reason"] == "healthy_to_router"

    def test_no_port_data(self):
        v = decide(_signals(port_link=None))
        assert v["side"] == "unclear"
        assert v["action"] == "instruct"
        assert v["reason"] == "no_port_data"

    def test_every_branch_returns_full_envelope(self):
        for s in (
            _signals(billing_suspended=True),
            _signals(incident={"description": "x"}),
            _signals(switch_status="inactive"),
            _signals(port_link="down"),
            _signals(observed_mac="FF:FF:FF:FF:FF:FF"),
            _signals(dhcp_status="expired"),
            _signals(),
        ):
            v = decide(s)
            assert set(v) == {"side", "group", "action", "reason", "agent_message"}
            assert v["side"] in ("provider", "customer", "unclear")
            assert v["action"] in ("inform", "create_ticket", "instruct")


class TestDiagnoseSeedScenarios:
    """Integration: the seeded S1-S5 customers produce the promised verdicts."""

    def _diagnose(self, customer_id: str) -> dict:
        from agent.tools import diagnose_connection

        result = diagnose_connection(customer_id)
        assert result["success"] is True, result
        return result["verdict"]

    def test_s1_billing(self, db_connection):
        v = self._diagnose("CUST101")
        assert v["group"] == "B1"
        assert v["action"] == "inform"

    def test_s2_mass_outage(self, db_connection):
        v = self._diagnose("CUST102")
        assert v["group"] == "B2"
        assert v["action"] == "inform"

    def test_s3_switch_unreachable(self, db_connection):
        v = self._diagnose("CUST103")
        assert v["group"] == "B3"
        assert v["action"] == "create_ticket"
        assert v["reason"] == "switch_unreachable"

    def test_s4_link_down_neighbors_up(self, db_connection):
        v = self._diagnose("CUST104")
        assert v["group"] == "B4/B5"
        assert v["action"] == "instruct"

    def test_s5a_foreign_mac(self, db_connection):
        v = self._diagnose("CUST105")
        assert v["group"] == "B6"
        assert v["reason"] == "foreign_mac"

    def test_s5b_factory_reset_dhcp(self, db_connection):
        v = self._diagnose("CUST106")
        assert v["group"] == "B6"
        assert v["reason"] == "dhcp_silent"

    def test_healthy_customer_unclear(self, db_connection):
        """A healthy seeded customer (Ginkūnai) falls through to B7/unclear."""
        v = self._diagnose("CUST109")
        assert v["group"] == "B7"
        assert v["side"] == "unclear"

    def test_missing_customer_id(self, db_connection):
        from agent.tools import diagnose_connection

        result = diagnose_connection("")
        assert result["success"] is False
        assert result["error"] == "missing_customer_id"
