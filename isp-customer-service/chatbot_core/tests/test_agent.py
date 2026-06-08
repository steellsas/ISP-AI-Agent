"""
Tests for agent logic (without real LLM calls where possible).

These tests verify agent stepping (native tool calling), tool descriptions,
and basic logic. The LLM is mocked so no network/API key is needed.
Run: pytest tests/test_agent.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import patch


def _fake_message(content=None, tool_calls=None):
    """Build a stand-in for the litellm assistant message object."""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _fake_tool_call(call_id, name, arguments):
    """Build a stand-in for a single litellm tool_call (arguments is a JSON str)."""
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class TestAgentStep:
    """Tests for ReactAgent.step() under native tool calling (LLM mocked)."""

    def test_step_text_reply(self):
        """A message with no tool_calls becomes the customer reply."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        msg = _fake_message(content="Labas! Kuo galiu padėti?")
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            result = agent.step(user_input="Labas")

        assert result["action"] == "respond"
        assert result["response"] == "Labas! Kuo galiu padėti?"
        assert result["needs_continuation"] is False
        # Reply is persisted as a plain assistant message.
        assert agent.state.messages[-1] == {
            "role": "assistant",
            "content": "Labas! Kuo galiu padėti?",
        }

    def test_step_tool_call(self):
        """A tool_call is executed and recorded as a role:'tool' message."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        tc = _fake_tool_call("call_1", "search_knowledge", '{"query": "lėtas internetas"}')
        msg = _fake_message(content=None, tool_calls=[tc])
        observation = json.dumps({"success": True, "results": []})

        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
            patch("agent.react_agent.execute_tool", return_value=observation) as exec_mock,
        ):
            result = agent.step(user_input="Lėtas internetas")

        # Tool was executed with parsed args, loop must continue.
        exec_mock.assert_called_once_with("search_knowledge", {"query": "lėtas internetas"})
        assert result["needs_continuation"] is True
        assert result["response"] is None
        assert result["action"] == "search_knowledge"
        assert result["tool_calls"][0]["name"] == "search_knowledge"

        # History: assistant(tool_calls) followed by a tool result keyed by id.
        assistant_msg = agent.state.messages[-2]
        tool_msg = agent.state.messages[-1]
        assert assistant_msg["tool_calls"][0]["function"]["name"] == "search_knowledge"
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        assert tool_msg["content"] == observation

    def test_step_empty_reply_retries(self):
        """No tool call and empty content should trigger a corrective retry."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        msg = _fake_message(content="")
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            result = agent.step(user_input="Labas")

        assert result["response"] is None
        assert result["needs_continuation"] is True

    def test_step_updates_customer_state(self):
        """find_customer tool result should populate customer state."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        tc = _fake_tool_call("call_1", "find_customer", '{"phone": "+37060012345"}')
        msg = _fake_message(content=None, tool_calls=[tc])
        observation = json.dumps(
            {
                "success": True,
                "customer_id": "CUST-1",
                "name": "Jonas",
                "addresses": [{"address": "Vilnius, Gatvė 1"}],
            }
        )

        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
            patch("agent.react_agent.execute_tool", return_value=observation),
        ):
            agent.step(user_input="Neveikia internetas")

        assert agent.state.customer_id == "CUST-1"
        assert agent.state.customer_name == "Jonas"


class TestAgentSystemPrompt:
    """Tests for agent system prompt."""

    def test_system_prompt_contains_tools(self):
        """System prompt should include tool descriptions."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert "find_customer" in agent.system_prompt
        assert "search_knowledge" in agent.system_prompt
        assert "check_network_status" in agent.system_prompt

    def test_system_prompt_has_informal_instructions(self):
        """System prompt should specify informal tone."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        system_prompt_lower = agent.system_prompt.lower()

        # Should mention informal/tu form
        assert "informal" in system_prompt_lower or "tu" in system_prompt_lower

    def test_system_prompt_has_rag_instructions(self):
        """System prompt should instruct to use search_knowledge."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        system_prompt_lower = agent.system_prompt.lower()

        assert "search_knowledge" in system_prompt_lower
        assert "knowledge" in system_prompt_lower


class TestAgentState:
    """Tests for agent state management."""

    def test_agent_state_has_caller_phone(self):
        """Agent state should have caller phone."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert agent.state.caller_phone == "+37060012345"

    def test_agent_state_starts_empty(self):
        """New agent should have empty messages."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert len(agent.state.messages) == 0
        assert agent.state.is_complete == False

    def test_agent_phone_in_system_prompt(self):
        """Caller phone should be in system prompt."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert "+37060012345" in agent.system_prompt

    def test_agent_state_customer_info_initially_none(self):
        """Customer info should be None initially."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert agent.state.customer_id is None
        assert agent.state.customer_name is None


class TestAgentStateClass:
    """Tests for AgentState dataclass."""

    def test_state_set_customer_info(self):
        """Should set customer info correctly."""
        from agent.state import AgentState

        state = AgentState(caller_phone="+37060012345")
        state.set_customer_info(
            customer_id="CUST001", name="Jonas Jonaitis", address="Vilnius, Gedimino g. 1"
        )

        assert state.customer_id == "CUST001"
        assert state.customer_name == "Jonas Jonaitis"
        assert state.customer_address == "Vilnius, Gedimino g. 1"

    def test_state_confirm_address(self):
        """Should confirm address and set caller name."""
        from agent.state import AgentState

        state = AgentState(caller_phone="+37060012345")
        state.confirm_address(caller_name="Petras")

        assert state.address_confirmed == True
        assert state.caller_name == "Petras"

    def test_state_to_dict(self):
        """Should convert to dict correctly."""
        from agent.state import AgentState

        state = AgentState(caller_phone="+37060012345")
        state.customer_id = "CUST001"

        data = state.to_dict()

        assert isinstance(data, dict)
        assert data["caller_phone"] == "+37060012345"
        assert data["customer_id"] == "CUST001"


class TestAgentConfig:
    """Tests for agent configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from agent.config import get_config

        config = get_config()

        assert config.max_turns == 20
        assert config.temperature == 0.3
        assert config.language == "lt"

    def test_update_config(self):
        """Should update config values."""
        from agent.config import get_config, update_config

        update_config(max_turns=30)
        config = get_config()

        assert config.max_turns == 30

        # Reset
        update_config(max_turns=20)


class TestToolDescriptions:
    """Tests for tool descriptions generation."""

    def test_get_tools_description(self):
        """Should generate valid tools description."""
        from agent.tools import get_tools_description

        description = get_tools_description()

        assert isinstance(description, str)
        assert "find_customer" in description
        assert "search_knowledge" in description
        assert len(description) > 100

    def test_tools_description_has_parameters(self):
        """Tools description should include parameters."""
        from agent.tools import get_tools_description

        description = get_tools_description()

        assert "phone" in description.lower()
        assert "query" in description.lower()
        assert "customer_id" in description.lower()


class TestToolValidation:
    """Tests for Tool.validate_arguments() and execute_tool() guarding."""

    def _tools_by_name(self):
        from agent.tools import REAL_TOOLS

        return {t.name: t for t in REAL_TOOLS}

    def test_validate_drops_unknown(self):
        """Unknown argument keys are dropped (with warning) and validation passes."""
        find_customer = self._tools_by_name()["find_customer"]

        cleaned, error = find_customer.validate_arguments({"phone": "+37060012345", "bogus": "x"})

        assert error is None
        assert cleaned == {"phone": "+37060012345"}  # 'bogus' dropped
        assert "bogus" not in cleaned

    def test_validate_missing_required(self):
        """Missing a required parameter returns a structured error, no cleaned args."""
        search_knowledge = self._tools_by_name()["search_knowledge"]

        cleaned, error = search_knowledge.validate_arguments({})

        assert cleaned == {}
        assert error is not None
        assert error["error"] == "invalid_arguments"
        assert error["tool"] == "search_knowledge"
        assert error["missing_required"] == ["query"]

    def test_validate_coerces_scalar_to_string(self):
        """A scalar passed where a string is declared is coerced to str."""
        check_network_status = self._tools_by_name()["check_network_status"]

        cleaned, error = check_network_status.validate_arguments({"customer_id": 123})

        assert error is None
        assert cleaned == {"customer_id": "123"}
        assert isinstance(cleaned["customer_id"], str)

    def test_validate_non_dict_arguments(self):
        """Non-dict arguments are rejected with a structured error."""
        find_customer = self._tools_by_name()["find_customer"]

        cleaned, error = find_customer.validate_arguments("not a dict")

        assert cleaned == {}
        assert error is not None
        assert error["error"] == "invalid_arguments"

    def test_execute_tool_missing_required_returns_error(self):
        """execute_tool short-circuits on missing required args (no function call)."""
        from agent.tools import execute_tool

        # search_knowledge requires 'query'; with none, validation must stop it
        # BEFORE touching the knowledge base.
        observation = execute_tool("search_knowledge", {})
        data = json.loads(observation)

        assert data["error"] == "invalid_arguments"
        assert data["missing_required"] == ["query"]

    def test_execute_tool_unknown_tool(self):
        """execute_tool returns an error for an unknown tool name."""
        from agent.tools import execute_tool

        observation = execute_tool("nonexistent_tool", {})
        data = json.loads(observation)

        assert "Unknown tool" in data["error"]


class TestAgentBuildMessages:
    """Tests for message building."""

    def test_build_messages_includes_system(self):
        """Built messages should include system prompt."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        messages = agent._build_messages()

        assert len(messages) >= 1
        assert messages[0]["role"] == "system"
        assert "find_customer" in messages[0]["content"]

    def test_build_messages_with_user_input(self):
        """Should add user input to messages."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        messages = agent._build_messages(user_input="Labas")

        # Should have system + user message
        assert len(messages) >= 2
        assert messages[-1]["role"] == "user"
        assert "Labas" in messages[-1]["content"]


class TestPromptLoader:
    """Tests for prompt loading."""

    def test_load_system_prompt(self):
        """Should load and format system prompt."""
        from agent.prompts import load_system_prompt

        prompt = load_system_prompt(
            tools_description="- test_tool: Test description",
            caller_phone="+37060012345",
            language="lt",  # Specify Lithuanian
        )

        assert isinstance(prompt, str)
        assert "+37060012345" in prompt
        assert "test_tool" in prompt
        assert "Lithuanian" in prompt
