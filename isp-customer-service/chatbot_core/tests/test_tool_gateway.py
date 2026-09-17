"""
ToolGateway (agent/tooling) — the one place a tool call happens.

Run: pytest tests/test_tool_gateway.py -v
"""

import json

from agent.tooling import ToolGateway

from tests.calls import make_agent


class _Tracer:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


class _Provider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def available_tools(self):
        return []

    def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return json.dumps(self.result)


def _agent(provider):
    tracer = _Tracer()
    agent = make_agent("+37060012353", tracer=tracer)
    agent.tools = ToolGateway(provider)
    tracer.events.clear()
    return agent, tracer


class TestToolGateway:
    def test_call_is_traced_once_with_its_reason(self):
        provider = _Provider({"success": True, "affected": False, "active_outages": []})
        agent, tracer = _agent(provider)

        result = agent.tools.run(
            agent.state,
            agent.runtime,
            "check_outages",
            {"area": "Šiauliai, Dainų g."},
            reason="test_reason",
        )

        calls = [e for e in tracer.events if e["type"] == "tool_call"]
        results = [e for e in tracer.events if e["type"] == "tool_result"]
        assert len(calls) == 1 and calls[0]["reason"] == "test_reason"
        assert len(results) == 1 and results[0]["ok"] is True
        assert provider.calls == [("check_outages", {"area": "Šiauliai, Dainų g."})]
        assert result.gated is False and result.data["affected"] is False

    def test_gate_refusal_never_reaches_the_provider(self):
        provider = _Provider({"success": True})
        agent, tracer = _agent(provider)  # not identified yet

        result = agent.tools.run(
            agent.state,
            agent.runtime,
            "diagnose_connection",
            {"customer_id": "CUST009"},
            reason="test",
        )

        assert result.gated is True and result.data["error"] == "not_identified"
        assert provider.calls == []
        assert [e["type"] for e in tracer.events].count("tool_call") == 1

    def test_observation_updates_state_unless_read_only(self):
        observation = {"success": True, "case_closed": True, "reason": "resolved"}
        agent, _ = _agent(_Provider(observation))
        agent.state.identity.customer_id = "CUST009"

        agent.tools.run(
            agent.state,
            agent.runtime,
            "close_case",
            {"reason": "declined"},
            reason="test",
            apply=False,
        )
        assert agent.state.closing.case_closed is False

        agent.tools.run(
            agent.state, agent.runtime, "close_case", {"reason": "declined"}, reason="test"
        )
        assert agent.state.closing.case_closed is True


class TestTelemetry:
    _VERDICT = {
        "success": True,
        "verdict": {"reason": "router_hung", "side": "customer", "group": "B6"},
        "signals": {"traffic": "none"},
    }

    def test_snapshot_commits_the_verdict(self):
        from agent.tooling import telemetry

        agent, tracer = _agent(_Provider(self._VERDICT))
        agent.state.identity.customer_id = "CUST112"

        telemetry(agent.state, agent.runtime, mode="snapshot", reason="test")

        assert agent.state.diagnosis.verdicts["network"]["reason"] == "router_hung"
        assert agent.state.diagnosis.hypothesis["cause"] == "router_hung"
        assert agent.state.resolution.procedure["verdict"] == "router_hung"
        call = next(e for e in tracer.events if e["type"] == "tool_call")
        assert call["name"] == "diagnose_connection" and call["reason"] == "snapshot:test"

    def test_recheck_never_changes_verdict_or_hypothesis(self):
        from agent.tooling import telemetry

        agent, _ = _agent(_Provider(self._VERDICT))
        agent.state.identity.customer_id = "CUST112"
        agent.state.diagnosis.hypothesis = {"cause": "foreign_mac", "status": "testing"}

        result = telemetry(agent.state, agent.runtime, mode="recheck", reason="test")

        assert result.data["verdict"]["reason"] == "router_hung"
        assert agent.state.diagnosis.verdicts == {}
        assert agent.state.diagnosis.hypothesis == {"cause": "foreign_mac", "status": "testing"}
        assert agent.state.resolution.procedure is None


class TestNoToolCallsOutsideTooling:
    def test_engine_code_never_bypasses_the_gateway(self):
        import re
        from pathlib import Path

        agent_dir = Path(__file__).resolve().parents[1] / "src" / "agent"
        pattern = re.compile(r"execute_tool\(|from crm_mcp|from network_diagnostic_mcp")
        offenders = [
            f"{path.relative_to(agent_dir)}:{n}"
            for path in agent_dir.rglob("*.py")
            if path.name != "tools.py" and "tooling" not in path.parts
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if pattern.search(line)
        ]
        assert offenders == []
