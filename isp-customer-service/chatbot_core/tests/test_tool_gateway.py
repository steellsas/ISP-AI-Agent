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
        observation = {"success": True, "affected": True}
        agent, _ = _agent(_Provider(observation))
        agent.state.identity.customer_id = "CUST009"
        args = {"customer_id": "CUST009"}

        agent.tools.run(
            agent.state, agent.runtime, "check_outages", args, reason="test", apply=False
        )
        assert agent.state.diagnosis.outage_reported is False

        agent.tools.run(agent.state, agent.runtime, "check_outages", args, reason="test")
        assert agent.state.diagnosis.outage_reported is True


class TestManifestGuards:
    """Wave 2c: how often a tool may run is its manifest's `guards`, counted on the call's
    own state — so a checkpoint resume cannot hand the caller a second port reset."""

    def test_an_action_runs_once_per_call(self):
        provider = _Provider({"success": True})
        agent, _ = _agent(provider)
        agent.state.identity.customer_id = "CUST009"
        args = {"customer_id": "CUST009"}

        first = agent.tools.run(agent.state, agent.runtime, "reset_port", args, reason="fix")
        second = agent.tools.run(agent.state, agent.runtime, "reset_port", args, reason="fix")

        assert first.gated is False
        assert second.gated is True and second.data["error"] == "guard_max_per_call"
        assert provider.calls == [("reset_port", args)]  # the second never reached it
        assert agent.state.tools.calls["reset_port"] == 1

    def test_a_refused_call_is_not_counted(self):
        """A guard must not be fed by calls the gate itself refused."""
        agent, _ = _agent(_Provider({"success": True}))  # nobody identified
        agent.tools.run(agent.state, agent.runtime, "reset_port", {}, reason="fix")
        assert agent.state.tools.calls == {}

    def test_the_trace_says_what_kind_of_tool_ran(self):
        agent, tracer = _agent(_Provider({"success": True, "active_outages": []}))
        agent.tools.run(
            agent.state, agent.runtime, "check_outages", {"customer_id": "C"}, reason="t"
        )
        call = next(e for e in tracer.events if e["type"] == "tool_call")
        assert call["capability"] == "outages" and call["adapter"] == "demo_db"

    def test_a_cooldown_and_the_hours_are_read_from_the_manifest(self):
        """No manifest uses these yet (they arrive with real equipment actions), so the
        guard itself is tested against a manifest built here."""
        import time

        from agent.contract.schema import ToolManifest
        from agent.tooling.gateway import _guards

        agent, _ = _agent(_Provider({"success": True}))
        spec = ToolManifest(
            tool="reboot_cpe",
            capability="action",
            adapter="demo_db",
            timeout_s=8,
            guards={"cooldown_s": 600, "allowed_hours": "08-22"},
            on_failure={"say_key": "tools.unavailable_action", "fallback": "ticket"},
            audit=True,
        )

        assert _guards(agent.state, "reboot_cpe", spec) is None  # never run in this call
        agent.state.tools.last_at["reboot_cpe"] = time.time() - 10
        refusal = _guards(agent.state, "reboot_cpe", spec)
        assert refusal and json.loads(refusal)["error"] == "guard_cooldown"

        agent.state.tools.last_at.clear()
        night = ToolManifest(**{**spec.model_dump(), "guards": {"allowed_hours": "03-04"}})
        hour = time.localtime().tm_hour
        refusal = _guards(agent.state, "reboot_cpe", night)
        if hour in (3,):
            assert refusal is None
        else:
            assert refusal and json.loads(refusal)["error"] == "guard_hours"


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
