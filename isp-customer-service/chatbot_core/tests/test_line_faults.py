"""
NT tinklo gedimai (Andrius 2026-09-11): linija nutrūkusi iki buto
(link_down_local) ir CRC klaidos (crc_errors) — the seeded customers reach the right
card, and the ticket says why honestly. (The v1 pack-walk tests went with the packs.)
"""


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
