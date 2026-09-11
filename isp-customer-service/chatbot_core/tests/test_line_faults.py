"""
NT tinklo gedimai (Andrius 2026-09-11): linija nutrūkusi iki buto
(link_down_local) ir CRC klaidos (crc_errors) — ability-first pack'ai su
variklio linijos patikra po laido perkišimo (rh_check šablonas linijai).
"""

import pytest


def _agent(verdict, step, monkeypatch, reason_now):
    from agent import walker_flow
    from agent.react_agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060030305")
    agent.state.customer_id = "CUST305"
    agent.state.problem_type = "internet_down"
    agent.state.resolution = {"verdict": verdict, "step": step, "asked": True}
    monkeypatch.setattr(ReactAgent, "_fresh_diagnose_reason", lambda self: reason_now)
    assert walker_flow  # imported for parity with other suites
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


class TestAdvanceLineCheck:
    """Variklis perskaito liniją ir sulieja su kliento žodžiu."""

    def test_line_still_down_escalates_honestly(self, db_connection, monkeypatch):
        agent = _agent("link_down_local", "ll_recheck", monkeypatch, "link_down_local")
        agent._advance_line_check(agent.state.resolution, "Taip, viskas gerai dabar")
        r = agent.state.resolution
        assert r["step"] == "escalate"  # žodis „gerai" NEnusveria linijos fakto
        assert "kabelio pažeidimas" in r["escalate_reason"]

    def test_line_ok_caller_yes_resolves(self, db_connection, monkeypatch):
        agent = _agent("link_down_local", "ll_recheck", monkeypatch, "healthy_to_router")
        agent._advance_line_check(agent.state.resolution, "Taip, atsirado internetas!")
        assert agent.state.case_closed and agent.state.closed_reason == "resolved"
        assert agent.state.ticket_id is None

    def test_line_ok_caller_no_escalates(self, db_connection, monkeypatch):
        agent = _agent("crc_errors", "crc_recheck", monkeypatch, "healthy_to_router")
        agent._advance_line_check(agent.state.resolution, "Ne, vis tiek neveikia")
        assert agent.state.resolution["step"] == "escalate"

    def test_unclear_with_recovered_line_holds(self, db_connection, monkeypatch):
        agent = _agent("crc_errors", "crc_recheck", monkeypatch, "healthy_to_router")
        agent._advance_line_check(agent.state.resolution, "Nu palaukit, žiūriu")
        assert agent.state.resolution["step"] == "crc_recheck"  # laikoma, perklausiama


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


class TestBlendGuard:
    """Gyvas 2026-09-11: „perkišau, nepadėjo" per carry-through uždarė kaip
    resolved. Blend žingsniai (ll/crc_recheck) — variklio, žodis jų nevaro."""

    def test_nepadejo_at_cable_never_resolves(self, db_connection, monkeypatch):
        from agent.resolution import get_strategy

        agent = _agent("crc_errors", "crc_cable", monkeypatch, "crc_errors")
        st = get_strategy("crc_errors")
        agent._advance_instruct(
            agent.state.resolution,
            st.step("crc_cable"),
            st,
            "Gal ir užlenkės, bet perkišau, nepadėjo",
        )
        r = agent.state.resolution
        assert r["step"] == "crc_recheck"  # patikros klausimas eina, byla NEuždaryta
        assert not agent.state.case_closed

    def test_restored_vocabulary_negations(self, db_connection):
        from agent.resolution import Outcome, detect_restored

        assert detect_restored("Perkišau, bet nepadėjo") is Outcome.NO
        assert detect_restored("Nieko nepasikeitė") is Outcome.NO
        assert detect_restored("Internetas nedirba") is Outcome.NO
        # „jo" liko YES tik kaip atskiras žodis
        assert detect_restored("Jo") is Outcome.YES
        assert detect_restored("Jo, jau veikia") is Outcome.YES

    def test_still_down_at_closing_reopens(self, db_connection, monkeypatch):
        from types import SimpleNamespace

        from agent.graph_v2.nodes.closing import make_closing_node

        agent = _agent("crc_errors", "crc_recheck", monkeypatch, "healthy_to_router")
        s = agent.state
        s.case_closed = True
        s.closed_reason = "resolved"
        node = make_closing_node(agent)
        upd = node(SimpleNamespace(turn=SimpleNamespace(user_input="Internetas neveikia.")))
        assert upd["turn"].reply  # registracijos dialogas, ne „geros dienos"
        assert "geros dienos" not in upd["turn"].reply.lower()
        assert not s.is_complete
        assert "vis tiek neveikia" in (s.resolution.get("escalate_reason") or "")


@pytest.mark.usefixtures("db_connection")
class TestAbilityEntry:
    def test_ability_no_routes_to_homework(self, db_connection):
        from agent.resolution import get_strategy, next_step_id

        st = get_strategy("link_down_local")
        assert next_step_id(st, "ll_ability", "no") == "ll_homework"
        assert next_step_id(st, "ll_homework", "yes") == "callback"
