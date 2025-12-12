"""
Tests for ReAct agent logic (without LLM calls where possible).

These tests verify agent parsing, tool descriptions, and basic logic.
Run: pytest tests/test_agent.py -v
"""

import pytest
import json


class TestAgentParsing:
    """Tests for agent response parsing."""

    def test_parse_respond_action(self):
        """Should parse respond action correctly."""
        from agent.react_agent import ReactAgent
        
        agent = ReactAgent(caller_phone="+37060012345")
        
        # Simulate LLM response
        response = '''Thought: Customer needs help
Action: respond
Action Input: {"message": "Labas! Kuo galiu padėti?"}'''
        
        thought, action, action_input = agent._parse_response(response)
        
        assert action == "respond"
        assert action_input["message"] == "Labas! Kuo galiu padėti?"
        assert "Customer needs help" in thought

    def test_parse_tool_action(self):
        """Should parse tool action correctly."""
        from agent.react_agent import ReactAgent
        
        agent = ReactAgent(caller_phone="+37060012345")
        
        response = '''Thought: Need to find customer
Action: find_customer
Action Input: {"phone": "+37060012345"}'''
        
        thought, action, action_input = agent._parse_response(response)
        
        assert action == "find_customer"
        assert action_input["phone"] == "+37060012345"

    def test_parse_search_knowledge_action(self):
        """Should parse search_knowledge action correctly."""
        from agent.react_agent import ReactAgent
        
        agent = ReactAgent(caller_phone="+37060012345")
        
        response = '''Thought: Need to search for slow internet solutions
Action: search_knowledge
Action Input: {"query": "lėtas internetas"}'''
        
        thought, action, action_input = agent._parse_response(response)
        
        assert action == "search_knowledge"
        assert action_input["query"] == "lėtas internetas"

    def test_parse_finish_action(self):
        """Should parse finish action correctly."""
        from agent.react_agent import ReactAgent
        
        agent = ReactAgent(caller_phone="+37060012345")
        
        response = '''Thought: Issue resolved
Action: finish
Action Input: {"summary": "Problema išspręsta"}'''
        
        thought, action, action_input = agent._parse_response(response)
        
        assert action == "finish"
        assert "summary" in action_input

    def test_parse_malformed_json(self):
        """Should handle malformed JSON gracefully."""
        from agent.react_agent import ReactAgent
        
        agent = ReactAgent(caller_phone="+37060012345")
        
        response = '''Thought: Test
Action: respond
Action Input: not valid json'''
        
        thought, action, action_input = agent._parse_response(response)
        
        # Should not crash, action should be parsed
        assert action == "respond"


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
            customer_id="CUST001",
            name="Jonas Jonaitis",
            address="Vilnius, Gedimino g. 1"
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
        from agent.config import update_config, get_config
        
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
            language="lt"  # Specify Lithuanian
        )
        
        assert isinstance(prompt, str)
        assert "+37060012345" in prompt
        assert "test_tool" in prompt
        assert "Lithuanian" in prompt 
