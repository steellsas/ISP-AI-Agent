"""
NT tinklo gedimai (Andrius 2026-09-11): linija nutrūkusi iki buto
(link_down_local) ir CRC klaidos (crc_errors) — ability-first pack'ai su
variklio linijos patikra po laido perkišimo (rh_check šablonas linijai).
"""

import pytest


def _agent(verdict, step, monkeypatch, reason_now):

    from tests.calls import make_agent

    agent = make_agent("+37060030305")
    agent.state.identity.customer_id = "CUST305"
    agent.state.intake.problem_type = "internet_down"
    agent.state.resolution.procedure = {"verdict": verdict, "step": step, "asked": True}
    monkeypatch.setattr(
        "agent.execute.diagnosis.fresh_diagnose_reason", lambda state, rt: reason_now
    )
    return agent


class TestPacksBuild:
    def test_link_down_local_strategy(self, db_connection):
        from agent.resolution import get_strategy

        st = get_strategy("link_down_local")
        assert st is not None
        ids = [s.id for s in st.steps]
        assert ids == [
            "ll_ability",
            "ll_locate",
            "ll_homework",
            "ll_lights",
            "ll_wan",
            "ll_power",
            "ll_cable",
            "ll_recheck",
            "escalate",
        ]
        assert st.step("ll_homework").on == {"yes": "callback", "no": "escalate"}
        # Aiškus simptomas (Andrius): po bendrų lempučių — INTERNETO lemputė.
        assert st.step("ll_lights").on == {"yes": "ll_wan", "no": "ll_power"}

    def test_crc_strategy(self, db_connection):
        from agent.resolution import get_strategy

        st = get_strategy("crc_errors")
        assert st is not None
        assert [s.id for s in st.steps] == [
            "crc_ability",
            "crc_locate",
            "crc_homework",
            "crc_cable",
            "crc_recheck",
            "escalate",
        ]

    def test_honest_ticket_need_from_packs(self, db_connection):
        from agent.evidence import fault_need

        assert "kabelio pažeidimas" in fault_need("link_down_local")
        assert "laid" in fault_need("crc_errors")


class TestSeeds:
    def test_crc_customer_gets_crc_verdict(self, db_connection):
        import json

        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST305"}))
        assert d["success"] and d["verdict"]["reason"] == "crc_errors"

    def test_unregistered_node_fault(self, db_connection):
        import json

        from agent.tools import execute_tool

        d = json.loads(execute_tool("diagnose_connection", {"customer_id": "CUST306"}))
        assert d["success"] and d["verdict"]["reason"] == "node_fault_unregistered"
        assert d["verdict"]["side"] == "provider"


@pytest.mark.usefixtures("db_connection")
class TestAbilityEntry:
    def test_ability_no_routes_to_homework(self, db_connection):
        from agent.resolution import get_strategy, next_step_id

        st = get_strategy("link_down_local")
        assert next_step_id(st, "ll_ability", "no") == "ll_homework"
        assert next_step_id(st, "ll_homework", "yes") == "callback"
