"""
ToolGateway (agent/tooling) — the one place a tool call happens.

Run: pytest tests/test_tool_gateway.py -v
"""

import json
import time
from unittest.mock import patch

from agent.contract import limits
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


class TestSlowAndBrokenTools:
    """Wave 2c-3: the demo answers in ~1 ms, production in seconds — and sometimes not at
    all. The manifest's timeout decides, and the failure observation carries the plan."""

    class _SlowProvider:
        def __init__(self, delay: float, result=None):
            self.delay = delay
            self.calls = []
            self.result = result or {"success": True}

        def available_tools(self):
            return []

        def execute(self, tool_name, arguments):
            self.calls.append((tool_name, arguments))
            time.sleep(self.delay)
            return json.dumps(self.result)

    class _BrokenProvider:
        def __init__(self, fail_times=99):
            self.fail_times = fail_times
            self.calls = []

        def available_tools(self):
            return []

        def execute(self, tool_name, arguments):
            self.calls.append((tool_name, arguments))
            if len(self.calls) <= self.fail_times:
                raise RuntimeError("NMS unreachable")
            return json.dumps({"success": True})

    def _with_timeout(self, agent, name, seconds, **over):
        """Run `name` as if its manifest allowed only `seconds` (patching the manifest is
        how a contract test exercises a timeout without waiting for a real one)."""
        from agent.contract import tools as manifests

        spec = manifests.manifest(name)
        tight = spec.model_copy(update={"timeout_s": seconds, **over})
        return patch.object(manifests, "manifest", lambda n, _t=tight: _t if n == name else None)

    def test_a_tool_that_does_not_answer_returns_its_fallback(self):
        provider = self._SlowProvider(0.3)
        agent, tracer = _agent(provider)
        agent.state.identity.customer_id = "CUST009"

        with self._with_timeout(agent, "diagnose_connection", 0.05):
            result = agent.tools.run(
                agent.state,
                agent.runtime,
                "diagnose_connection",
                {"customer_id": "CUST009"},
                reason="snapshot",
            )

        assert result.data["error"] == "tool_timeout"
        assert result.data["fallback"] == "ask_client"  # what the caller cannot see, we ask
        assert result.data["say_key"] == "tools.unavailable_probe"
        timeouts = [e for e in tracer.events if e["type"] == "tool_timeout"]
        assert len(timeouts) == 1 and timeouts[0]["alert"] == "ops"

    def test_a_read_only_lookup_is_retried_but_an_action_is_not(self):
        """A repeated probe is harmless; a repeated port reset is not — it may have landed."""
        probe = self._BrokenProvider(fail_times=1)
        agent, _ = _agent(probe)
        agent.state.identity.customer_id = "CUST009"
        with self._with_timeout(agent, "resolve_address", 5, retries=1):
            result = agent.tools.run(
                agent.state, agent.runtime, "resolve_address", {"city": "Šiauliai"}, reason="id"
            )
        assert result.data["success"] is True and len(probe.calls) == 2

        action = self._SlowProvider(0.3)
        agent2, _ = _agent(action)
        agent2.state.identity.customer_id = "CUST009"
        with self._with_timeout(agent2, "reset_port", 0.05, retries=1):
            result2 = agent2.tools.run(
                agent2.state,
                agent2.runtime,
                "reset_port",
                {"customer_id": "CUST009"},
                reason="fix",
            )
        assert result2.data["error"] == "tool_timeout"
        assert result2.data["fallback"] == "ticket" and len(action.calls) == 1

    def test_an_action_that_timed_out_is_counted_so_it_cannot_run_again(self):
        provider = self._SlowProvider(0.3)
        agent, _ = _agent(provider)
        agent.state.identity.customer_id = "CUST009"
        with self._with_timeout(agent, "reset_port", 0.05):
            agent.tools.run(
                agent.state, agent.runtime, "reset_port", {"customer_id": "CUST009"}, reason="fix"
            )
        assert agent.state.tools.calls["reset_port"] == 1

    def test_a_broken_adapter_says_what_the_caller_hears(self):
        provider = self._BrokenProvider()
        agent, tracer = _agent(provider)
        agent.state.identity.customer_id = "CUST009"
        with self._with_timeout(agent, "create_ticket", 5, retries=0):
            result = agent.tools.run(
                agent.state,
                agent.runtime,
                "create_ticket",
                {"customer_id": "CUST009"},
                reason="register",
            )
        assert result.data["error"] == "tool_error"
        assert result.data["say_key"] == "tools.unavailable_ticket"
        assert any(e["type"] == "tool_error" for e in tracer.events)

    def test_a_slow_answer_is_traced_with_the_line_to_say(self):
        provider = self._SlowProvider(0.12)
        agent, tracer = _agent(provider)
        agent.state.identity.customer_id = "CUST009"
        with patch.object(limits, "get", lambda name: 50 if name == "tool_slow_ms" else 5):
            agent.tools.run(
                agent.state,
                agent.runtime,
                "diagnose_connection",
                {"customer_id": "CUST009"},
                reason="snapshot",
            )
        slow = [e for e in tracer.events if e["type"] == "tool_slow"]
        assert len(slow) == 1 and slow[0]["filler_key"] == "system.filler"


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
