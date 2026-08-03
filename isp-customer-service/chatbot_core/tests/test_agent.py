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

        assert config.max_turns == 50
        assert config.temperature == 0.3
        assert config.language == "lt"

    def test_update_config(self):
        """Should update config values."""
        from agent.config import get_config, update_config

        update_config(max_turns=30)
        config = get_config()

        assert config.max_turns == 30

        # Reset
        update_config(max_turns=50)


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


class TestHistoryWindow:
    """Tests for history pruning (windowing) and durable-fact injection."""

    def test_short_history_not_pruned(self):
        """History at or below the window is returned unchanged."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.config.history_window_messages = 10
        agent.state.messages = [{"role": "user", "content": f"m{i}"} for i in range(5)]

        pruned = agent._prune_history(agent.state.messages)

        assert pruned == agent.state.messages

    def test_window_zero_disables_pruning(self):
        """A window of 0 sends the full history."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.config.history_window_messages = 0
        agent.state.messages = [{"role": "user", "content": f"m{i}"} for i in range(50)]

        pruned = agent._prune_history(agent.state.messages)

        assert len(pruned) == 50

    def test_long_history_pruned_to_window(self):
        """A long, tool-free history is trimmed to exactly the window size."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.config.history_window_messages = 6
        # 20 alternating user/assistant text messages (no tool exchanges)
        agent.state.messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(20)
        ]

        pruned = agent._prune_history(agent.state.messages)

        assert len(pruned) == 6
        assert pruned[-1]["content"] == "m19"

    def test_prune_never_starts_on_orphaned_tool(self):
        """
        If the window boundary lands on a tool result, it must expand left to
        include the assistant(tool_calls) that owns it — otherwise the chat API
        rejects the orphaned tool message.
        """
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.config.history_window_messages = 3
        # ...older..., assistant(tool_calls), tool, tool, assistant(text)
        agent.state.messages = [
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old2"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
            {"role": "tool", "tool_call_id": "a", "content": "r1"},
            {"role": "tool", "tool_call_id": "b", "content": "r2"},
            {"role": "assistant", "content": "done"},
        ]

        pruned = agent._prune_history(agent.state.messages)

        # window=3 would start on a tool result (index 3); must back up to the
        # assistant that issued the tool_calls (index 2).
        assert pruned[0].get("role") == "assistant"
        assert pruned[0].get("tool_calls") is not None
        # No tool result may appear without its owning assistant before it.
        assert pruned[0]["role"] != "tool"

    def test_build_messages_injects_known_facts(self):
        """Resolved AgentState facts ride in a SEPARATE trailing system message,
        not concatenated into the (cacheable) system prompt."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.state.set_customer_info(
            customer_id="C123",
            name="Jonas Jonaitis",
            address="Vilniaus g. 1, Vilnius",
        )

        messages = agent._build_messages(user_input="Labas")

        # The system prefix stays byte-stable (cache-friendly) — no facts in it.
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == agent.system_prompt
        assert "C123" not in messages[0]["content"]

        # The facts live in a later system message, before the trailing user turn.
        fact_msgs = [m for m in messages[1:] if m["role"] == "system" and "C123" in m["content"]]
        assert len(fact_msgs) == 1
        facts = fact_msgs[0]["content"]
        assert "Jonas Jonaitis" in facts
        assert "Vilniaus g. 1, Vilnius" in facts
        assert messages[-1]["role"] == "user"  # user input stays last

    def test_state_facts_block_none_when_empty(self):
        """No facts resolved yet -> no addendum (system prompt unchanged)."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert agent._state_facts_block() is None
        messages = agent._build_messages()
        assert messages[0]["content"] == agent.system_prompt

    def test_facts_block_surfaces_heard_address(self):
        """NLU-prefilled slots are surfaced so the model passes them to
        resolve_address instead of re-extracting garbled text (R5)."""
        from agent.react_agent import ReactAgent
        from agent.slots import SlotStatus

        agent = ReactAgent(caller_phone="+37060012345")
        agent.state.profile.street.propose("Aušros g.", 0.8, SlotStatus.HEARD)
        agent.state.profile.house.propose("8", 0.8, SlotStatus.HEARD)

        facts = agent._state_facts_block()
        assert "HEARD ADDRESS" in facts
        assert "street=Aušros g." in facts
        assert "house=8" in facts

    def test_heard_address_hidden_once_identified(self):
        """Once identified the heard-address hint is dropped (already known)."""
        from agent.react_agent import ReactAgent
        from agent.slots import SlotStatus

        agent = ReactAgent(caller_phone="+37060012345")
        agent.state.profile.street.propose("Aušros g.", 0.8, SlotStatus.HEARD)
        agent.state.customer_id = "CUST110"

        facts = agent._state_facts_block()
        assert "HEARD ADDRESS" not in (facts or "")

    def test_diagnosis_captured_and_surfaced(self, db_connection):
        """diagnose_connection findings become durable case state (Pillar A1)."""
        import json

        from agent.react_agent import ReactAgent
        from agent.tools import diagnose_connection

        agent = ReactAgent(caller_phone="+37060020105")
        obs = json.dumps(diagnose_connection("CUST105"))  # S5a -> B6 foreign_mac
        agent._update_state_from_observation("diagnose_connection", obs)

        assert agent.state.diagnosis["network"]["group"] == "B6"
        assert agent.state.diagnosis["network"]["reason"] == "foreign_mac"

        facts = agent._state_facts_block()
        assert "DIAGNOSTIKA [network] (B6" in facts
        assert "kitas įrenginys (MAC)" in facts  # the LT gloss


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


class TestDeterministicInformClose:
    """INFORM mode (outage/billing/no-strategy) closes deterministically on a farewell —
    the engine, not the model, ends the call (fixes the goodbye loop observed live)."""

    def _informed_agent(self):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020102")
        agent.state.customer_id = "CUST102"
        agent.state.diagnosis["network"] = {"group": "B2", "reason": "active_outage"}
        agent.state.outage_reported = True
        agent.state.resolution = None  # inform mode: no strategy to walk
        return agent

    def test_farewell_closes_outage_call(self, db_connection):
        agent = self._informed_agent()
        agent._maybe_close_inform("Ačiū, viso gero, sudie")
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "outage"
        assert agent.state.is_complete is True

    def test_no_farewell_keeps_call_open(self, db_connection):
        agent = self._informed_agent()
        agent._maybe_close_inform("O kada tiksliai sutvarkysite?")
        assert agent.state.case_closed is False

    def test_active_strategy_never_closed_here(self, db_connection):
        """A live troubleshooting strategy belongs to the walker — a mid-flow 'ne'
        must not end the call."""
        agent = self._informed_agent()
        agent.state.outage_reported = False
        agent.state.diagnosis["network"] = {"group": "B6", "reason": "foreign_mac"}
        agent.state.resolution = {"verdict": "foreign_mac", "step": "confirm_change"}
        agent._maybe_close_inform("ne")
        assert agent.state.case_closed is False


class TestEscalateOutcome:
    """Phase 3.11 B: the ESCALATE step is a deterministic OUTCOME — the ENGINE
    registers the ticket from state on consent; the model no longer calls
    create_ticket. Classifier off -> the keyword consent reader drives routing."""

    def _agent_on_escalate(self, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.diagnosis["network"] = {"group": "B6", "reason": "no_mac_observed"}
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "escalate",
            "asked": True,  # the consent question was posed last turn
        }
        return agent

    def test_consent_registers_ticket_and_closes(self, db_connection, monkeypatch):
        agent = self._agent_on_escalate(monkeypatch)
        agent._walk_resolution("gerai, tinka")
        assert agent.state.ticket_id  # engine-created, from state
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "registered"

    def test_decline_closes_without_ticket(self, db_connection, monkeypatch):
        agent = self._agent_on_escalate(monkeypatch)
        agent._walk_resolution("ne, nenoriu, ačiū")
        assert agent.state.ticket_id is None
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "declined"

    def test_unclear_holds_the_step(self, db_connection, monkeypatch):
        agent = self._agent_on_escalate(monkeypatch)
        agent._walk_resolution("hmm palaukite sekundėlę")
        assert agent.state.ticket_id is None
        assert agent.state.case_closed is False  # re-ask, don't register on a garble

    def test_not_asked_yet_never_advances(self, db_connection, monkeypatch):
        agent = self._agent_on_escalate(monkeypatch)
        agent.state.resolution["asked"] = False
        agent._walk_resolution("gerai, tinka")  # "taip" to something else entirely
        assert agent.state.ticket_id is None
        assert agent.state.case_closed is False


class TestAutoRegisterEscalate:
    """consent=False ESCALATE (dr_register_router): the registration is a necessity —
    the engine registers ON ARRIVAL and closes; no consent question, no misread."""

    def test_arrival_registers_and_closes(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_register_router"}

        ran = agent.ensure_action_done()

        assert ran is True
        assert agent.state.ticket_id
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "registered"

    def test_lauksiu_skambucio_is_consent_not_decline(self):
        from agent.resolution import detect_ticket_consent

        assert detect_ticket_consent("Lauksiu skambučio, ačiū") == "yes"

    def test_farewell_stt_garbles_close(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Neturiu, neturiu, visą gerą") is True
        assert detect_farewell("visa gera, ačiū") is True


class TestRestoredPreAnswer:
    """A clear 'atsirado / veikia' fused with the goodbye pre-answers the restored
    CONFIRM before it was asked — the resolve gets RECORDED instead of the call dying
    unclosed on the hangup (observed live: resolved Wi-Fi call left outcome=None)."""

    def test_restored_yes_advances_unasked_verify(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060020109")
        agent.state.customer_id = "CUST109"
        agent.state.problem_type = "internet_down"
        agent.state.diagnosis["network"] = {"group": "B7", "reason": "healthy_to_router"}
        agent.state.hypothesis = {"cause": "healthy_to_router", "status": "testing"}
        agent.state.resolution = {
            "verdict": "healthy_to_router",
            "step": "cs_verify_dev",
            "asked": False,  # the question was never posed — caller pre-answered
        }

        agent._walk_resolution("Įjungta, yra internetas, ačiū, atsirado. Viso gero.")

        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "resolved"


class TestAddressGuards:
    """Round-3 live bugs: a garbled reply must not commit the offered address, and a
    post-identification correction must reopen identification."""

    def test_garbled_taip_nebija_is_not_a_confirm(self):
        from agent.resolution import detect_address_confirm

        assert detect_address_confirm("Taip, nebija") is None  # mixed -> re-ask
        assert detect_address_confirm("Taip, tvirtinu") == "yes"
        assert detect_address_confirm("Ne, dėl kito adreso") == "no"
        # Problem words are not denials: "neveikia" alongside taip still confirms.
        assert detect_address_confirm("Taip, neveikia internetas dėl to adreso") == "yes"

    def test_pre_turn_guard_vetoes_commit(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 3?"}
        )
        agent._pre_turn_guards("Taip, nebija")
        assert agent._addr_confirm_note is not None  # veto: do not resolve the offer
        facts = agent._state_facts_block()
        assert facts and "NEPATVIRTINTAS" in facts

    def test_correction_reopens_identification(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.customer_id = "CUST101"
        agent.state.customer_address = "Šiauliai, Tilžės g. 60-3"
        agent.state.diagnosis["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent._pre_turn_guards("Tai ne dėl to adresų skambinu")
        assert agent.state.customer_id is None  # identity dropped
        assert agent.state.diagnosis == {}  # per-account conclusions dropped
        assert agent._reopen_note is True


class TestRefuseOrTicket:
    """A refusal / explicit ticket demand ends troubleshooting in a registration."""

    def _agent_mid_flow(self, monkeypatch, step="cable_check"):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060020105")
        agent.state.customer_id = "CUST105"
        agent.state.problem_type = "internet_down"
        agent.state.hypothesis = {"cause": "foreign_mac", "status": "testing"}
        agent.state.resolution = {"verdict": "foreign_mac", "step": step, "asked": True}
        return agent

    def test_demand_registers_immediately(self, db_connection, monkeypatch):
        agent = self._agent_mid_flow(monkeypatch)
        agent._walk_resolution("Nieko nedarysiu, įregistruokit gedimą")
        assert agent.state.ticket_id
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "registered"

    def test_refuse_routes_to_escalate_consent(self, db_connection, monkeypatch):
        agent = self._agent_mid_flow(monkeypatch)
        agent._walk_resolution("Aš nenamosiu")  # garbled refusal
        r = agent.state.resolution
        assert r["step"] == "escalate"  # polite consent question comes next
        assert agent.state.ticket_id is None  # not registered yet — clarify first
        assert "atsisakė" in r["escalate_reason"]


class TestAddressSpeech:
    def test_spoken_address_form(self):
        from agent.voice_pipeline import normalize_lt_address_speech as n

        assert n("Ar skambinate dėl Tilžės g. 60-7?") == (
            "Ar skambinate dėl Tilžės gatvė, namas 60, butas 7?"
        )
        assert n("Radau: Žeimių g. 12, butas 6") == "Radau: Žeimių gatvė 12, butas 6"
        assert n("Jokio adreso čia nėra") == "Jokio adreso čia nėra"


class TestIdentificationLadder:
    """2026-07-31: identification ends with WHO-is-calling (record, never a gate);
    the check result is deferred one turn behind that question. A clearly dictated
    correction address is resolved by the ENGINE (no LLM tool hesitancy)."""

    def test_caller_intro_captured_and_result_released(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.customer_id = "CUST101"
        agent.state.diagnosis["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent._result_pending = True  # the caller question was posed last reply

        agent._pre_turn_guards("Ona, aš žmona sutartį sudariusio")

        assert agent.state.caller_name == "Ona, aš žmona sutartį sudariusio"
        assert agent.state.caller_relation == "family"
        # The RESULT directive now renders (deferred news released this turn).
        facts = agent._state_facts_block()
        assert facts and "REZULTATO PRISTATYMAS" in facts

    def test_relation_keywords(self):
        from agent.identification import detect_caller_relation

        assert detect_caller_relation("Jonas, taip, aš sutartį sudaręs") == "holder"
        assert detect_caller_relation("Petras, nuomininkas") == "tenant"
        assert detect_caller_relation("kaimynas, padedu senolei") == "helper"
        assert detect_caller_relation("mmm") == "unknown"

    def test_engine_resolves_dictated_correction(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020105")  # phone = 60-7 account
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 7?"}
        )
        agent._prefill_slots_from_text("Ne, skambinu dėl Tilžės gatvės 60 buto 3")
        agent._pre_turn_guards("Ne, skambinu dėl Tilžės gatvės 60 buto 3")

        # The ENGINE committed the corrected identity and diagnosed silently.
        assert agent.state.customer_id == "CUST101"
        assert agent.state.diagnosis["network"]["reason"] == "billing_suspended"
        # The reply is steered by the identified-note (ladder: caller question next).
        assert agent._addr_confirm_note and "IDENTIFIKUOTA" in agent._addr_confirm_note
        assert agent._result_pending is True

    def test_farewell_garble_visai_gero(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Ne visai gero") is True


class TestVoiceGuardsRound5:
    """2026-08-03 live round: garbles must not close calls or climb steps."""

    def test_long_ne_sentence_is_not_a_farewell(self):
        from agent.resolution import detect_farewell

        # This exact garble hung up on the caller mid-ladder (observed live).
        assert detect_farewell("Ne, mano vardas Tomas, aš esu kaimynas") is False
        assert detect_farewell("Ne, ačiū") is True  # short goodbyes still work
        assert detect_farewell("viso gero") is True

    def test_backchannel_holds_asking_steps(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_offer_bridge",
            "asked": True,
        }

        agent._walk_resolution("T.")  # was read as "yes, I have a computer" live
        assert agent.state.resolution["step"] == "dr_offer_bridge"  # held
        agent._walk_resolution("Mhm.")
        assert agent.state.resolution["step"] == "dr_offer_bridge"  # held

    def test_caller_intro_with_stt_question_mark_is_captured(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.customer_id = "CUST101"
        agent.state.diagnosis["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent._result_pending = True

        agent._pre_turn_guards("Tomas? Ne, mano vardas Tomas, aš esu kaimynas.")
        assert agent.state.caller_name is not None  # captured, not skipped as a question
        assert agent.state.caller_relation == "helper"

    def test_inform_close_gated_until_news_told(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.customer_id = "CUST101"
        agent.state.diagnosis["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent._result_pending = True  # ladder still open, news NOT delivered

        agent._maybe_close_inform("viso gero")
        assert agent.state.case_closed is False  # must NOT hang up before informing

    def test_farewell_mid_strategy_confirms_then_registers(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}

        agent._pre_turn_guards("viso gero")  # mid-troubleshooting goodbye
        assert agent._end_confirm_pending is True
        assert agent.state.case_closed is False  # clarify first, never hang up
        reply = agent._identification_scripted_reply("viso gero")
        assert reply and "tikrai norite baigti" in reply

        agent._pre_turn_guards("taip, baikim")  # confirmed -> outcome: registration
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "registered"
        assert agent.state.ticket_id

    def test_farewell_mid_strategy_declined_resumes(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}

        agent._pre_turn_guards("viso gero")
        agent._pre_turn_guards("ne ne, tęskime")  # changed their mind
        assert agent.state.case_closed is False
        assert agent._end_confirm_pending is False
        agent._walk_resolution("ne ne, tęskime")  # held one turn, not misrouted
        assert agent.state.resolution["step"] == "dr_lights"


class TestAnalysisStep2:
    """Step 2 — the ANALYSIS object: the caller's anamnesis is read, fuses into the
    hypothesis evidence, and rides on the record and the ticket."""

    def test_extract_anamnesis_readings(self):
        from agent.nlu import extract_anamnesis

        r = extract_anamnesis("Šįryt dingo, po audros")
        assert r == {"when": "šiandien", "trigger": "audra"}
        assert extract_anamnesis("Nežinau, dingo ir viskas")["when"] == "nežino"
        assert extract_anamnesis("Vakar dar veikė")["when"] == "vakar"

    def test_hypothesis_cites_both_sides(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.anamnesis_when = "šiandien"
        agent.state.anamnesis_trigger = "audra"
        agent._open_hypothesis("no_mac_observed")

        because = " ".join(agent.state.hypothesis["because"])
        assert "klientas sako" in because and "audra" in because

    def test_ticket_carries_anamnesis(self, db_connection, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_when = "vakar"
        agent.state.anamnesis_trigger = "audra"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_register_router"}

        agent.ensure_action_done()  # consent-free registration on arrival

        assert agent.state.ticket_id
        import sqlite3

        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "Klientas: dingo vakar, po: audra" in details
