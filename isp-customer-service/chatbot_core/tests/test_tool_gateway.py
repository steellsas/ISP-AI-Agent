"""
ToolGateway (agent/tooling) — the one place a tool call happens.

Run: pytest tests/test_tool_gateway.py -v
"""

import json

from agent.react_agent import ReactAgent
from agent.tooling import ToolGateway


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
    agent = ReactAgent(caller_phone="+37060012353", tracer=tracer)
    agent.tools = ToolGateway(provider)
    tracer.events.clear()
    return agent, tracer


class TestToolGateway:
    def test_call_is_traced_once_with_its_reason(self):
        provider = _Provider({"success": True, "affected": False, "active_outages": []})
        agent, tracer = _agent(provider)

        result = agent.tools.run(
            agent, "check_outages", {"area": "Šiauliai, Dainų g."}, reason="test_reason"
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
            agent, "diagnose_connection", {"customer_id": "CUST009"}, reason="test"
        )

        assert result.gated is True and result.data["error"] == "not_identified"
        assert provider.calls == []
        assert [e["type"] for e in tracer.events].count("tool_call") == 1

    def test_observation_updates_state_unless_read_only(self):
        observation = {"success": True, "case_closed": True, "reason": "resolved"}
        agent, _ = _agent(_Provider(observation))
        agent.state.identity.customer_id = "CUST009"

        agent.tools.run(agent, "close_case", {"reason": "declined"}, reason="test", apply=False)
        assert agent.state.closing.case_closed is False

        agent.tools.run(agent, "close_case", {"reason": "declined"}, reason="test")
        assert agent.state.closing.case_closed is True
