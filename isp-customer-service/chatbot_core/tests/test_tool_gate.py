"""
Tests for the deterministic tool-access gate (ReactAgent._gate_tool).

Phase 3.5 §5: technical tools (diagnose/update_mac/reset_port/create_ticket) are
blocked until the customer is identified, and may never run on a customer_id that
is not the identified one. This moves "no diagnostics before identification" and
"never act on a guessed id" from the prompt into code (kills the customer_id='1'
hallucination seen in trace 20260618-091508).

Run: pytest tests/test_tool_gate.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _fake_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _fake_tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.fixture
def agent():
    from agent.react_agent import ReactAgent

    return ReactAgent(caller_phone="+37060012345")


class TestGateUnit:
    def test_blocks_diagnose_when_not_identified(self, agent):
        out = agent._gate_tool("diagnose_connection", {"customer_id": "1"})
        assert out is not None
        assert json.loads(out)["error"] == "not_identified"

    @pytest.mark.parametrize(
        "tool", ["diagnose_connection", "update_mac", "reset_port", "create_ticket"]
    )
    def test_all_technical_tools_gated(self, agent, tool):
        assert agent._gate_tool(tool, {}) is not None

    def test_allows_when_identified_and_id_matches(self, agent):
        agent.state.customer_id = "CUST105"
        assert agent._gate_tool("diagnose_connection", {"customer_id": "CUST105"}) is None

    def test_id_mismatch_blocked(self, agent):
        agent.state.customer_id = "CUST105"
        out = agent._gate_tool("diagnose_connection", {"customer_id": "CUST101"})
        assert out is not None
        assert json.loads(out)["error"] == "id_mismatch"

    def test_non_gated_tools_always_pass(self, agent):
        for tool in ("resolve_address", "find_customer", "check_outages", "search_knowledge"):
            assert agent._gate_tool(tool, {"anything": 1}) is None

    def test_identified_tool_without_id_arg_passes(self, agent):
        # e.g. a technical tool that doesn't echo customer_id in args
        agent.state.customer_id = "CUST105"
        assert agent._gate_tool("reset_port", {}) is None


class TestOutageGate:
    """check_outages must be street-specific (city-only returns other streets)."""

    def test_city_only_blocked(self, agent):
        out = agent._gate_tool("check_outages", {"area": "Šiauliai"})
        assert out is not None
        assert json.loads(out)["error"] == "city_only"

    def test_street_level_passes(self, agent):
        assert agent._gate_tool("check_outages", {"area": "Šiauliai, Dainų g."}) is None

    def test_by_customer_id_passes(self, agent):
        assert agent._gate_tool("check_outages", {"customer_id": "CUST105"}) is None

    def test_no_args_passes(self, agent):
        assert agent._gate_tool("check_outages", {}) is None


class TestCloseCaseGate:
    """close_case reason-specific backstop against premature/unfounded closes."""

    def test_resolved_blocked_when_not_identified(self, agent):
        out = agent._gate_tool("close_case", {"reason": "resolved"})
        assert out is not None
        assert json.loads(out)["error"] == "not_identified"

    def test_resolved_allowed_when_identified(self, agent):
        agent.state.customer_id = "CUST105"
        assert agent._gate_tool("close_case", {"reason": "resolved"}) is None

    def test_outage_blocked_without_outage_reported(self, agent):
        out = agent._gate_tool("close_case", {"reason": "outage"})
        assert out is not None
        assert json.loads(out)["error"] == "no_outage"

    def test_outage_allowed_after_outage_reported(self, agent):
        agent.state.outage_reported = True
        assert agent._gate_tool("close_case", {"reason": "outage"}) is None

    def test_declined_always_allowed(self, agent):
        assert agent._gate_tool("close_case", {"reason": "declined"}) is None


class TestGateInStep:
    def test_blocked_call_does_not_execute_tool(self, agent):
        """A premature diagnose is intercepted; execute_tool is never called."""
        tc = _fake_tool_call("c1", "diagnose_connection", '{"customer_id": "1"}')
        msg = _fake_message(content=None, tool_calls=[tc])

        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
            patch("agent.react_agent.execute_tool") as exec_mock,
        ):
            result = agent.step(user_input="neveikia internetas")

        exec_mock.assert_not_called()
        obs = json.loads(result["tool_calls"][0]["observation"])
        assert obs["error"] == "not_identified"
        assert result["needs_continuation"] is True
