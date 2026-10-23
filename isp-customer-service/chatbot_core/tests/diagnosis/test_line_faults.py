"""
NT tinklo gedimai (Andrius 2026-09-11): linija nutrūkusi iki buto
(link_down_local) ir CRC klaidos (crc_errors) — the seeded customers reach the right
card, and the ticket says why honestly. (The v1 pack-walk tests went with the packs.)
"""

FUNCTION = "Konkretūs gedimai"


class TestTicketNeed:
    def test_honest_ticket_need_from_cards(self, db_connection):
        from agent.evidence import fault_need

        assert "kabelio pažeidimas" in fault_need("link_down_local")
        assert "laid" in fault_need("crc_errors")


class TestSeeds:
    def test_crc_customer_gets_crc_verdict(self, db_connection):
        import json

        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST305"}))
        assert d["success"]
        from agent.case import candidates
        from agent.facts import facts_from_signals

        matched = {
            c.fault for c in candidates(facts_from_signals(d["signals"])) if c.status == "matched"
        }
        assert matched == {"crc_errors"}

    def test_unregistered_node_fault(self, db_connection):
        import json

        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST306"}))
        assert d["success"]
        from agent.case import candidates
        from agent.facts import facts_from_signals

        matched = {
            c.fault for c in candidates(facts_from_signals(d["signals"])) if c.status == "matched"
        }
        assert matched == {"node_fault_unregistered"}  # wave 4: a news card
        # "the provider side" is now what the news card says, not a field in the payload


class TestTheLineReadThroughTheCards:
    """The bind check and the background refresh read the line through the cards: telemetry
    has carried no `verdict` since wave 4, so both read None and every bind looked „fixed"
    (found 2026-10-22)."""

    def _line(self, customer_id):
        import json

        from agent.execute.diagnosis import line_fault
        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": customer_id}))
        return line_fault(d["signals"])

    def test_each_demo_line_reads_as_its_card(self, db_connection):
        assert self._line("CUST112") == "router_hung"
        assert self._line("CUST001") == "no_mac_observed"
        assert self._line("CUST109") == "healthy_to_router"

    def test_no_reading_is_no_card(self):
        from agent.execute.diagnosis import line_fault

        assert line_fault(None) is None

    def test_a_bind_the_line_does_not_confirm_is_not_fixed(self, monkeypatch):
        import json

        from agent.execute import observe

        from tests.calls import make_runtime, make_state

        def tools(name, args):
            return {"success": True}

        state, rt = make_state("+37060020105"), make_runtime(fake_tools=tools)
        state.identity.customer_id = "CUST105"
        for still, fixed in (("foreign_mac", False), ("healthy_to_router", True), (None, False)):
            monkeypatch.setattr(
                "agent.execute.diagnosis.fresh_diagnose_reason", lambda s, r, f=still: f
            )
            out = json.loads(observe.chain_after_bind(state, rt, "update_mac", '{"success": true}'))
            assert (out["telemetry_after"], out["fixed"]) == (still, fixed)
