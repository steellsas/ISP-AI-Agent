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


class TestAgentSystemPrompt:
    """Tests for agent system prompt."""

    def test_system_prompt_contains_tools(self):
        """System prompt should include tool descriptions."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert "find_customer" in agent.system_prompt
        assert "search_knowledge" in agent.system_prompt
        assert "check_network_status" in agent.system_prompt


class TestAgentState:
    """Tests for agent state management."""

    def test_agent_phone_in_system_prompt(self):
        """Caller phone should be in system prompt."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        assert "+37060012345" in agent.system_prompt


class TestAgentStateClass:
    """Tests for AgentState dataclass."""

    def test_state_confirm_address(self):
        """Should confirm address and set caller name."""
        from agent.state import AgentState

        state = AgentState(caller_phone="+37060012345")
        state.confirm_address(caller_name="Petras")

        assert state.address_confirmed == True
        assert state.caller_name == "Petras"


class TestAgentConfig:
    """Tests for agent configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from agent.config import get_config

        config = get_config()

        assert config.max_turns == 50
        assert config.temperature == 0.3
        assert config.language == "lt"


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

    def test_state_facts_block_only_guard_when_empty(self):
        """Nothing resolved yet -> the only addendum is the pre-problem guard
        (2026-08-06: it stops the LLM offering the address before a problem is
        stated); the system prompt itself stays unchanged."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")

        facts = agent._state_facts_block()
        assert facts is not None and "PROBLEMA DAR NEPASAKYTA" in facts
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


def _complete_ticket_dialogue(agent):
    """Walk the 2-question contact dialogue (2026-08-04) to the registration.
    Each stage question must be ASKED before its answer counts (2026-08-05)."""
    agent._identification_scripted_reply(None)  # intro + phone question
    agent._pre_turn_guards("taip, tiks šis")
    agent._identification_scripted_reply("taip, tiks šis")  # hours question
    agent._pre_turn_guards("bet kada")
    return agent._identification_scripted_reply("bet kada")


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
        assert agent._ticket_stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
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


class TestHearingAgent:
    """2026-08-11 live fix: a barge-in-truncated "Ne." (meant "ne, nedega…") was
    read by the STALE dr_intro yes/no as "won't check" → escalate → ticket →
    dead call. Ownership: an open evidence question owns the reply; a bare
    negation CLARIFIES instead of driving one-way doors (escalate, ticket
    cancel); first evidence asks explain WHY (kodel from faults.yaml)."""

    def _agent(self, monkeypatch, step="dr_intro", asked=True):
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
            "step": step,
            "asked": asked,
        }
        return agent

    def test_bare_negation_detector(self):
        from agent.resolution import is_bare_negation

        assert is_bare_negation("Ne.")
        assert is_bare_negation("Ne, nežinau.")
        assert not is_bare_negation("Ne, nedega nei viena")  # carries an object
        assert not is_bare_negation("ne, nenoriu, ačiū")  # a real refusal
        assert not is_bare_negation("Gerai")
        assert not is_bare_negation(None)

    def test_walker_holds_while_evidence_question_open(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent._evidence_last_ask_key = "power_cable"
        agent._evidence_asks["power_cable"] = 1
        agent._walk_resolution("Ne.")  # the fatal live turn
        assert agent.state.resolution["step"] == "dr_intro"  # held, not escalate
        assert agent._ticket_stage is None

    def test_open_question_negation_gets_fault_file_clarify(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent._evidence_last_ask_key = "power_cable"
        agent._evidence_asks["power_cable"] = 1
        reply = agent._identification_scripted_reply("Ne.")
        assert reply is not None and "neįkištas" in reply  # patikslinimas wording

    def test_drive_negation_clarify_replaces_reask(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact

        agent = self._agent(monkeypatch)
        set_fact(agent.state.evidence, "device_present", "rado", CLIENT, 1)
        set_fact(agent.state.evidence, "lights", "nedega", CLIENT, 2)
        agent._evidence_last_ask_key = "power_cable"
        agent._evidence_asks["power_cable"] = 1
        reply = agent._evidence_drive("Ne.")
        assert reply is not None and "neįkištas" in reply

    def test_kodel_rides_on_first_evidence_ask(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact

        agent = self._agent(monkeypatch)
        set_fact(agent.state.evidence, "device_present", "rado", CLIENT, 1)
        reply = agent._evidence_drive("radau")
        assert reply is not None and "lemputė" in reply
        assert "maitinimą" in reply  # the kodel sentence

    def test_bare_ne_to_escalate_clarifies_once_then_escalates(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent._walk_resolution("Ne.")  # keyword "no" routes dr_intro -> escalate
        assert agent.state.resolution["step"] == "dr_intro"  # blocked — clarify instead
        assert agent._escalate_clarify_pending is True
        reply = agent._identification_scripted_reply("Ne.")
        assert reply is not None and "registruoju meistrą" in reply
        agent._walk_resolution("Ne.")  # repeated no IS a real no
        assert agent.state.resolution["step"] == "escalate"

    def test_rich_refusal_still_escalates_directly(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent._walk_resolution("Nieko nedarysiu, įregistruokit gedimą")
        assert agent._ticket_stage == "phone"  # refuse/demand path untouched

    def test_ticket_cancel_needs_one_confirm(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch, step="escalate")
        agent._ticket_stage = "phone"
        agent._ticket_ctx = {"phone_asked": True, "intro_done": True}
        agent._pre_turn_guards("Neregistruokite nieko")
        assert agent._ticket_stage == "phone"  # not cancelled yet
        reply = agent._ticket_stage_reply()
        assert "tikrai nereikia" in reply  # the confirm question went out
        agent._pre_turn_guards("nereikia")
        assert agent._ticket_stage == "cancelled"  # confirmed refusal cancels

    def test_ticket_cancel_confirm_can_resume(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch, step="escalate")
        agent._ticket_stage = "phone"
        agent._ticket_ctx = {"phone_asked": True, "intro_done": True}
        agent._pre_turn_guards("Neregistruokite nieko")
        agent._ticket_stage_reply()  # confirm question goes out
        agent._pre_turn_guards("gerai, registruokite vis dėlto")
        assert agent._ticket_stage == "phone"  # resumed, not cancelled
        assert "numeriu" in agent._ticket_stage_reply()  # stage re-asks

    # --- round 2 (live 2026-08-11, call 2) ------------------------------------

    def test_end_confirm_answer_never_routes_the_walker(self, db_connection, monkeypatch):
        # "Iki šau." (STT of "Įkišau") triggered confirm-end; the answer "Ne,
        # nenoriu" (= don't END) then advanced stale dr_intro -> escalate ->
        # ticket. The walker holds while the confirm-end answer is unread.
        agent = self._agent(monkeypatch)
        agent._end_confirm_pending = True
        agent._walk_resolution("Ne, nenoriu.")
        assert agent.state.resolution["step"] == "dr_intro"
        assert agent._ticket_stage is None

    def test_ticket_refusal_with_solving_content_returns_to_fix(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch, step="escalate")
        agent._ticket_stage = "phone"
        agent._ticket_ctx = {"phone_asked": True, "intro_done": True}
        agent._pre_turn_guards("Neregistruokite, pajunkim tą kompiuterį")
        assert agent._ticket_stage is None  # dialogue dropped…
        assert agent.state.case_closed is False  # …but the call stays OPEN
        assert agent._resume_fix_note is True  # narrator returns to the fix

    def test_cancel_confirm_answer_with_solving_content_returns_to_fix(
        self, db_connection, monkeypatch
    ):
        agent = self._agent(monkeypatch, step="escalate")
        agent._ticket_stage = "phone"
        agent._ticket_ctx = {
            "phone_asked": True,
            "intro_done": True,
            "cancel_confirm_asked": True,
            "cancel_confirm_out": True,
        }
        agent._pre_turn_guards("Ne, tai mes pajunkim tą kompiuterį. Aš jungiu kabelį.")
        assert agent._ticket_stage is None
        assert agent.state.case_closed is False
        assert agent._resume_fix_note is True

    # --- round 3 (live 2026-08-11, call 3) ------------------------------------

    def test_iki_is_a_preposition_not_a_goodbye(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Pajungtas iki galo.") is False  # killed a live bridge
        assert detect_farewell("Iki 17 valandos") is False  # ticket-hours answer
        assert detect_farewell("Iki šau.") is False  # STT of "Įkišau"
        assert detect_farewell("Iki!") is True
        assert detect_farewell("iki pasimatymo") is True
        assert detect_farewell("viso gero, iki") is True

    def test_bare_done_report_detector(self):
        from agent.resolution import is_bare_done_report

        assert is_bare_done_report("Mhm, patikrinau.")
        assert is_bare_done_report("Jau padariau")
        assert not is_bare_done_report("Patikrinau, laidas įkištas")
        assert not is_bare_done_report("Nedega nė viena")

    def test_plugged_detector_survives_stt_garbles(self):
        from agent.resolution import detect_plugged

        assert detect_plugged("Jau pajungiu.")  # missed live, instruction repeated 3×
        assert detect_plugged("Pajangių kompiuterį.")
        assert detect_plugged("Aš jau pajungiau kabelį")
        assert not detect_plugged("tuoj pajungsiu")  # future tense — not done yet

    def test_stale_step_question_reads_no_answers(self, db_connection, monkeypatch):
        # dr_intro presented ~15 turns earlier consumed "Dar interneto nėra."
        # as its own "no" -> escalate -> ticket (three live calls in a row).
        agent = self._agent(monkeypatch)
        agent.state.resolution["asked_at"] = 0
        agent.state.messages.extend({"role": "user", "content": f"turn {i}"} for i in range(8))
        agent._walk_resolution("Ne.")
        assert agent.state.resolution["step"] == "dr_intro"  # held — question too old
        assert agent._ticket_stage is None

    def test_fresh_step_question_still_routes(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent.state.resolution["asked_at"] = len(agent.state.messages)
        agent._walk_resolution("nieko nedarysiu, įregistruokit gedimą")
        assert agent._ticket_stage == "phone"  # refuse/demand path unaffected

    # --- round 4 (live 2026-08-11, call 4: bind never ran) --------------------

    def test_plug_report_reads_context_not_one_sentence(self, db_connection, monkeypatch):
        agent = self._agent(monkeypatch)
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Dabar įkiškite tą kabelį į kompiuterio tinklo lizdą — "
                "pasakykite, kai padarysite.",
            }
        )
        assert agent._plug_report("Ikišau, ikišau, laukiu internetą.") is True
        assert agent._plug_report("Taip, jis įkištas iki galo.") is True  # passive
        assert agent._plug_report("Pririškite tada.") is True  # explicit bind ask
        assert agent._plug_report("dar neprijungiau, sekundėlę") is False  # negation
        # The SAME words during the power-cable phase are NOT a bind report.
        agent.state.messages[-1] = {
            "role": "assistant",
            "content": "Patikrinkite, ar maitinimo laidas gerai įkištas į rozetę.",
        }
        assert agent._plug_report("Įkišau gerai.") is False

    def test_plug_report_memory_unlocks_the_bind_gate(self, db_connection, monkeypatch):
        # "Įkišau, laukiu" three turns ago — the gate demanded the verb in THIS
        # turn's utterance and kept repeating "Kai prijungsite…" (live).
        agent = self._agent(monkeypatch)
        agent._bridge_plug_reported = True
        agent._drive_bridge_offered = True
        reply = agent._drive_propose_fix("", "taip, viskas padaryta, laukiu")
        assert "Kai prijungsite" not in reply  # no more deferral on wording
        assert agent._bridge_bound or "nematome" in reply  # bind ran (or line check)

    def test_bailout_lands_on_declared_solution_step(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(monkeypatch)
        for k, v in (
            ("device_present", "rado"),
            ("lights", "nedega"),
            ("power_cable", "įkištas"),
            ("outlet_works", "bandyta"),
            ("has_computer", "yes"),
        ):
            set_fact(agent.state.evidence, k, v, CLIENT, 1)
        agent.state.caller_name = "Andrius"
        agent._recap_state = "done"
        agent._findings_announced = True
        agent._drive_bridge_offered = True
        agent._drive_repeats = 2  # distrust streak observed
        assert agent.solver_drive_turn("prijungiau, laukiu") is None  # walker resumes…
        assert agent.state.resolution["step"] == "dr_plug_pc"  # …AT the bridge

    # --- round 5 (2026-08-12): bridge-failure ladder ---------------------------

    def test_bridge_fail_ladder_lan_check_then_technician(self, db_connection, monkeypatch):
        # Plug reported, telemetry never shows the device (no simulation):
        # (1) say the line sees nothing + cable re-check, (2) the LAN question,
        # (3) incoming-cable note + technician, attempt on the ticket.
        agent = self._agent(monkeypatch)
        agent.state.caller_name = "Andrius"
        agent._bridge_plug_reported = True
        agent._drive_bridge_offered = True
        r1 = agent._drive_propose_fix("", "pajungiau kabelį")
        assert "nematome jūsų kompiuterio" in r1
        r2 = agent._drive_propose_fix("", "vis dar nieko")
        assert "LAN" in r2  # the computer's network card, not the router
        assert agent._evidence_last_ask_key == "lan_active"
        agent._ingest_client_evidence("Nerodo nieko, neaktyvus")
        assert agent.state.evidence["lan_active"]["value"] == "neaktyvus"
        r3 = agent._drive_propose_fix("", "ir dabar nieko")
        assert "kabeliu" in r3  # the possible incoming-cable problem is NAMED
        assert "Kokiu telefono numeriu" in r3  # technician registration begins
        assert "NEPAVYKO" in (agent._bridge_fail_note or "")
        _complete_ticket_dialogue(agent)
        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "NEPAVYKO" in details and "neaktyvus" in details

    def test_lan_pending_answers(self):
        from agent.evidence import read_pending_answer

        assert read_pending_answer("lan_active", "Rodo, kad aktyvus") == "aktyvus"
        assert read_pending_answer("lan_active", "Nerodo nieko") == "neaktyvus"
        assert read_pending_answer("lan_active", "dega lemputė prie lizdo") == "aktyvus"

    def test_on_task_question_stays_with_the_flow(self, db_connection, monkeypatch):
        # "Kur jungti tą kabelį į kompiuterį?" is a question ABOUT the current
        # instruction — side_topic answered it with "tai nėra mano sritis" live.
        agent = self._agent(monkeypatch)
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Dabar įkiškite tą kabelį į kompiuterio tinklo lizdą — "
                "pasakykite, kai padarysite.",
            }
        )
        assert agent.classify_side_topic("Kur jungti tą kabelį į kompiuterį?") is False
        # An off-task FAQ question still goes to the side node.
        assert agent.classify_side_topic("O kiek kainuos meistras?") is True


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
        assert agent._ticket_stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
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
        assert agent._ticket_stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
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

        assert agent.state.caller_name == "Ona"  # the NAME, not the sentence
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

        agent._pre_turn_guards("taip, baikim")  # confirmed -> contacts, then registration
        assert agent._ticket_stage == "phone"
        _complete_ticket_dialogue(agent)
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

        agent.ensure_action_done()  # consent-free: contacts dialogue on arrival
        _complete_ticket_dialogue(agent)

        assert agent.state.ticket_id
        import sqlite3

        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "Klientas: dingo vakar, po: audra" in details


class TestSideTopicNode:
    """2026-08-07: 'kiek kainuos?' was asked twice and ignored (the evidence
    drive has no question path); 'Aš skola kokia.' closed the call. Deviations
    now freeze the engine, answer from the FAQ and return to the anchor."""

    def _diagnosing(self, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}
        agent.state.last_question = "Pažiūrėkite, ar ant routerio dega bent viena lemputė."
        return agent

    def test_question_freezes_engine_and_flags_side_topic(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        assert agent.classify_side_topic("O kiek man tai kainuos?") is True
        assert agent.solver_drive_turn("O kiek man tai kainuos?") is None  # thinker yields
        agent._advance_resolution("O kiek man tai kainuos?")
        assert agent.state.resolution["step"] == "dr_lights"  # frozen, not advanced

    def test_side_facts_carry_faq_and_anchor(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        agent.state.last_heard = "O kiek man tai kainuos?"
        agent.classify_side_topic("O kiek man tai kainuos?")
        facts = agent._state_facts_block()
        assert "NUKRYPIMAS" in facts
        assert "nieko nekainuoja" in facts  # faq.yaml hit rides in
        assert "dega bent viena lemputė" in facts  # the return anchor

    def test_unknown_topic_gets_not_my_area_directive(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        agent.state.last_heard = "O koks rytoj oras Šiauliuose?"
        agent.classify_side_topic("O koks rytoj oras Šiauliuose?")
        facts = agent._state_facts_block()
        assert "ATSAKYMO NĖRA" in facts

    def test_third_deviation_is_scripted_frame(self, db_connection, monkeypatch):
        from agent.identification import phrase

        agent = self._diagnosing(monkeypatch)
        for q in ("O kiek kainuos?", "O koks oras?", "O kur jūsų ofisas?"):
            agent.classify_side_topic(q)
        reply = agent._identification_scripted_reply("O kur jūsų ofisas?")
        assert reply == phrase(
            "back_to_issue",
            inkaras="Pažiūrėkite, ar ant routerio dega bent viena lemputė.",
        )

    def test_third_deviation_with_confirmed_hypothesis_offers_choice(
        self, db_connection, monkeypatch
    ):
        from agent.identification import phrase

        agent = self._diagnosing(monkeypatch)
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._ingest_client_evidence("Laidas įkištas, bandžiau kitą rozetę")
        for q in ("O kiek kainuos?", "O koks oras?", "O kur jūsų ofisas?"):
            agent.classify_side_topic(q)
        reply = agent._identification_scripted_reply("O kur jūsų ofisas?")
        assert reply == phrase("solve_or_ticket")

    def test_informative_interruption_is_not_a_deviation(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        agent._side_topic_turns = 2
        assert agent.classify_side_topic("Kur ta lemputė? Nedega nė viena lemputė") is False
        assert agent._side_topic_turns == 0  # productive turn resets the streak

    def test_refusal_and_farewell_yield_to_walker_policies(self, db_connection, monkeypatch):
        import os

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._diagnosing(monkeypatch)
        # "neturiu laiko" got a solver wait->close and NO ticket live — the
        # thinker must hand policy turns to the walker + guards.
        assert agent.solver_drive_turn("Pala, aš nieko nedarysiu, neturiu laiko") is None
        assert agent.solver_drive_turn("gerai, viso gero") is None

    def test_hours_scrubbed_of_inner_question_marks(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)
        agent._pre_turn_guards("taip, tiks šis")
        agent._identification_scripted_reply("taip, tiks šis")
        agent._pre_turn_guards("Bet kada? Bet kurio laiko?")
        assert agent.state.contact_hours == "Bet kada Bet kurio laiko"

    def test_checking_cue_spoken_on_identity_commit(self, db_connection, monkeypatch):
        agent = self._diagnosing(monkeypatch)
        agent.state.resolution = None
        agent.state.customer_address = "Šiauliai, Vilniaus g. 29"
        agent._just_identified = True
        agent._result_pending = True
        reply = agent._identification_scripted_reply(None)
        assert "Tuoj patikrinsiu ryšį" in reply
        assert "su kuo kalbu" in reply


class TestFarewellPurity:
    def test_garbled_content_with_ne_is_not_a_farewell(self, db_connection):
        # Live 2026-08-10: "Ne daganiai 1." (=nedega nė viena) fast-forwarded
        # the ticket dialogue to done-with-defaults. The bare-"ne" fallback now
        # requires EVERY token to be a known closing word.
        from agent.resolution import detect_farewell

        assert detect_farewell("Ne daganiai 1.") is False
        assert detect_farewell("Ne viena") is False
        assert detect_farewell("Ne.") is True
        assert detect_farewell("Ne, ačiū") is True
        assert detect_farewell("viskas gerai") is True
        assert detect_farewell("viso gero") is True


class TestReviewGaps:
    """2026-08-07 architecture review fixes."""

    def test_reopen_clears_evidence_and_dialogue_state(self, db_connection, monkeypatch):
        # Stale-state bomb: after an address correction the OLD account's
        # telemetry facts (the verdict!) survived in the ledger.
        import os

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._update_state_from_observation(
            "diagnose_connection",
            json.dumps({"verdict": {"reason": "no_mac_observed", "side": "unclear"}}),
        )
        agent._begin_ticket_dialogue(None)
        agent._side_topic_turns = 2
        assert agent.state.evidence and agent._ticket_stage == "phone"

        agent._reopen_identification("skambinu dėl kito adreso — Dainų 5")

        assert agent.state.evidence == {}
        assert agent._ticket_stage is None and agent._ticket_ctx is None
        assert agent._evidence_asks == {} and agent._evidence_conflict is None
        assert agent._side_topic_turns == 0
        assert agent.state.customer_id is None  # identity dropped as before

    def test_scripted_turn_lands_user_message_on_history(self, db_connection):
        # The LLM narrator used to see holes: scripted turns never appended the
        # caller's utterance, so later turns re-asked answered questions.
        from agent.session import AgentSession

        s = AgentSession(caller_phone="+37060012353", engine="graph")
        s.greeting()
        reply = s.handle_turn("neveikia internetas")  # scripted anamnesis, no LLM
        assert "kada pastebėjote" in reply
        roles = [(m["role"], m.get("content")) for m in s.state.messages]
        assert ("user", "neveikia internetas") in roles
        assert roles[-1][0] == "assistant" and "kada pastebėjote" in roles[-1][1]

    def test_llm_turn_appends_user_exactly_once(self, db_connection):
        from unittest.mock import patch as _patch

        from agent.session import AgentSession

        def _stream(**kwargs):
            def _gen():
                yield "Atsakau."
                return _fake_message(content="Atsakau.")

            return _gen()

        s = AgentSession(caller_phone="+37060012353", engine="graph")
        s.greeting()
        with (
            _patch("agent.react_agent.stream_tool_completion", side_effect=_stream),
            _patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            s.handle_turn("O kas jūs tokie, kokia įmonė?")  # off-script -> LLM
        count = sum(
            1
            for m in s.state.messages
            if m.get("role") == "user" and m.get("content") == "O kas jūs tokie, kokia įmonė?"
        )
        assert count == 1  # pre-append did not double with the LLM loop


class TestBargeInCancel:
    """Phase 5 PR3: request_cancel stops the LLM generation ITSELF (the token
    loop closes the HTTP stream) and rolls the ask-bookkeeping back, so the
    interrupted question is re-asked. LangGraph never propagates an outer
    generator-close into the node (verified 2026-08-06) — the flag is the only
    reliable path."""

    def test_cancel_mid_generation_closes_llm_stream(self, db_connection):
        import time as _t

        closed = {"v": False}

        def slow_stream(**kwargs):
            def _gen():
                try:
                    for i in range(50):
                        _t.sleep(0.02)
                        yield f"tok{i} "
                    return _fake_message(content="pilnas atsakymas")
                except GeneratorExit:
                    closed["v"] = True
                    raise

            return _gen()

        from agent.session import AgentSession

        with (
            patch("agent.react_agent.stream_tool_completion", side_effect=slow_stream),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            s = AgentSession(caller_phone="unknown", engine="graph")
            s.greeting()
            tokens = []
            for tok in s.handle_turn_stream("O kas jūs tokie?"):
                tokens.append(tok)
                if len(tokens) == 3:
                    s.request_cancel()  # barge-in lands mid-generation
            assert closed["v"] is True  # the LLM stream was CLOSED, not drained
            assert len(tokens) < 50  # generation stopped early
            # The partial reply is on the record, marked as cut off.
            assert s.state.messages[-1]["role"] == "assistant"
            assert s.state.messages[-1]["content"].endswith("—")

    def test_cancel_keeps_asked_so_early_answers_route(self, db_connection):
        # Review 2026-08-07: callers interrupt BECAUSE they understood — a
        # blanket asked=False re-asked the question they just answered. The
        # flags stay; the NEXT turn decides (answer routes / question anchors /
        # unclear holds and re-asks naturally).
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}
        agent._evidence_asks["lights"] = 1
        agent._evidence_last_ask_key = "lights"

        agent.on_turn_cancelled("Pažiūrėkite, ar dega bent")

        assert agent.state.resolution["asked"] is True  # early answer will route
        assert agent._evidence_asks["lights"] == 0  # wording level not escalated
        assert agent.state.messages[-1]["content"].startswith("Pažiūrėkite")
        assert agent.state.messages[-1]["content"].endswith("—")

    def test_stale_cancel_never_kills_the_next_turn(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.request_cancel()  # interrupt raced past the turn's end
        reply = agent._identification_scripted_reply("Labadiena!")
        assert reply  # scripted path unaffected
        assert agent._cancel_requested is True  # cleared only at a STREAM turn start


class TestSmallTalkBeforeProblem:
    """Live 2026-08-06: "Labadiena!" fell to the LLM, which offered the address
    BEFORE any problem was stated; the ladder then re-offered it (duplicate).
    Small talk pre-problem is scripted now; the facts block guards the rest."""

    def _fresh(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="+37060012353")

    def test_greeting_gets_scripted_ask_problem(self, db_connection):
        from agent.identification import phrase

        agent = self._fresh()
        assert agent._identification_scripted_reply("Labadiena!") == phrase("ask_problem")
        assert agent._identification_scripted_reply("Sveiki") == phrase("ask_problem")

    def test_problem_statement_is_not_smalltalk(self, db_connection):
        agent = self._fresh()
        agent.state.problem_type = "internet_down"
        reply = agent._identification_scripted_reply("neveikia internetas")
        assert reply is not None and "kada pastebėjote" in reply  # anamnesis, not ask_problem

    def test_facts_forbid_address_offer_before_problem(self, db_connection):
        agent = self._fresh()
        facts = agent._state_facts_block() or ""
        assert "PROBLEMA DAR NEPASAKYTA" in facts
        agent.state.problem_type = "internet_down"
        facts2 = agent._state_facts_block() or ""
        assert "PROBLEMA DAR NEPASAKYTA" not in facts2


class TestScriptedWrapUp:
    """After the inform news, ANY non-question turn wraps up deterministically —
    a garbled goodbye ("Nusigaro") had looped 'nesupratau, pakartokite' forever."""

    def _informed(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020101")
        agent.state.customer_id = "CUST101"
        agent.state.diagnosis["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent._news_told = True
        return agent

    def test_garbled_goodbye_wraps_up(self, db_connection):
        agent = self._informed(db_connection)
        reply = agent._identification_scripted_reply("Nusigaro.")
        assert reply and "Ačiū, kad paskambinote" in reply
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "inform"
        assert agent.state.is_complete is True

    def test_question_after_news_goes_to_llm(self, db_connection):
        agent = self._informed(db_connection)
        assert agent._identification_scripted_reply("O kiek turiu sumokėti?") is None
        assert agent.state.case_closed is False

    def test_wants_more_goes_to_llm(self, db_connection):
        agent = self._informed(db_connection)
        assert agent._identification_scripted_reply("Palaukite, dar turiu klausimą") is None
        assert agent.state.case_closed is False


class TestThinkerBoundaries:
    """Step 3 — the mąstytojas drives piloted directions but NEVER overrides the
    deterministic mechanics (ladder, clarify contract, wrap-up)."""

    def _agent(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.caller_name = "Jonas"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_intro"}
        return agent

    def test_defers_while_ladder_open(self, db_connection, monkeypatch):
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent._result_pending = True  # caller-intro / result still owed
        assert agent.solver_drive_turn("taip") is None

    def test_defers_while_end_confirm_pending(self, db_connection, monkeypatch):
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent._end_confirm_pending = True
        assert agent.solver_drive_turn("taip") is None

    def test_defers_until_caller_intro_done(self, db_connection, monkeypatch):
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.caller_name = None  # ladder's last rung not done
        assert agent.solver_drive_turn("taip") is None

    def test_off_switch_reverts_to_walker(self, db_connection, monkeypatch):
        monkeypatch.setenv("SOLVER_DRIVE", "off")
        agent = self._agent(db_connection)
        assert agent.solver_drive_turn("taip") is None

    def test_non_piloted_direction_falls_back(self, db_connection, monkeypatch):
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.resolution = {"verdict": "foreign_mac", "step": "confirm_change"}
        assert agent.solver_drive_turn("taip") is None


class TestDriveRepeatBailout:
    """The thinker asked the SAME thing twice despite answers -> deterministic
    bailout to the registration offer (observed live: 6x verbatim loop)."""

    def test_distrust_loop_hands_wheel_to_walker(self, db_connection, monkeypatch):
        # Ledger v2: while EVIDENCE is missing, the evidence engine (not the
        # solver) asks — deterministically, bench or no bench. The distrust
        # bailout now matters where the SOLVER actually drives: the bridge
        # phase (evidence confirmed, has_computer=yes -> _evidence_drive None).
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.caller_name = "Andrius"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_power"}
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._ingest_client_evidence("Maitinimo laidas gerai įkištas, bandžiau kitą rozetę")
        agent._ingest_client_evidence("Turiu kompiuterį")
        agent._recap_state = "done"  # recap checkpoint tested elsewhere (round 3)
        agent._drive_repeats = 2  # repeat/disambiguate streak already observed

        assert agent.solver_drive_turn("gerai gerai") is None  # walker resumes
        assert agent._drive_disabled is True  # thinker benched for the rest of the call
        assert agent.solver_drive_turn("nedega") is None  # and stays benched

    def test_evidence_keeps_driving_after_solver_bench(self, db_connection, monkeypatch):
        # The rewind trap is dead: a benched solver no longer strands the call
        # at a stale step — missing evidence still gets asked deterministically.
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.caller_name = "Andrius"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_intro"}
        agent._drive_disabled = True  # solver already benched

        reply = agent.solver_drive_turn("na, nežinau")
        assert reply is not None and "Susiraskite routerį" in reply


class TestBindDiscipline:
    """2026-08-04 (Andrius): a change runs ONLY when the client did the work and
    agreed — the solver had the engine bind FOUR turns early, and its escalate
    wrote a raw verdict key as the ticket and lost ticket_id from the record."""

    def _driving_agent(self, monkeypatch, simulate="on"):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "SIMULATE_BRIDGE", simulate)
        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.caller_name = "Andrius"
        agent.state.anamnesis_when = "vakar"
        agent.state.anamnesis_trigger = "audra"
        agent.state.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_intro"}
        return agent

    def test_fix_deferred_until_plugged(self, db_connection, monkeypatch):
        agent = self._driving_agent(monkeypatch)
        # First deferral = the transition + bridge OFFER (2026-08-05); later
        # deferrals wait for the plug-in. Never a premature action either way.
        first = agent._drive_propose_fix("Pririšu dabar!", "gerai, tuoj bandysiu")
        assert "Ar turite kompiuterį" in first
        again = agent._drive_propose_fix("Pririšu dabar!", "gerai, tuoj bandysiu")
        assert "Kai prijungsite" in again
        assert agent._bridge_bound is False

    def test_plugged_report_binds_once(self, db_connection, monkeypatch):
        # Tools are FAKED so the shared session DB is not mutated (a real bind here
        # flipped CUST009 healthy and broke a later ordering-dependent graph test).
        import json as _json

        agent = self._driving_agent(monkeypatch)
        calls = []

        def fake_execute(name, args):
            calls.append(name)
            if name == "diagnose_connection":
                # After the (noop) simulation the line "sees" the plugged PC.
                reason = "foreign_mac" if "simulated" in calls else "no_mac_observed"
                return _json.dumps({"success": True, "verdict": {"reason": reason}})
            return _json.dumps({"success": True})

        monkeypatch.setattr("agent.react_agent.execute_tool", fake_execute)
        monkeypatch.setattr(agent, "_simulate_bridge_connection", lambda: calls.append("simulated"))
        monkeypatch.setattr(agent, "_augment_tool_result", lambda n, o: o)

        reply = agent._drive_propose_fix("", "Įkišau į kompiuterį")
        assert agent._bridge_bound is True
        assert "update_mac" in calls  # the bind actually ran
        assert "pririš" in reply.lower() or "atsirado" in reply.lower()
        # Never twice.
        again = agent._drive_propose_fix("", "įkišau dar kartą")
        assert "jau pririštas" in again
        assert calls.count("update_mac") == 1

    def test_drive_escalate_uses_state_ticket(self, db_connection, monkeypatch):
        agent = self._driving_agent(monkeypatch)
        q1 = agent._drive_escalate(None)
        assert "Kokiu telefono numeriu" in q1  # contacts dialogue first (2026-08-04)
        say = _complete_ticket_dialogue(agent)
        assert agent.state.ticket_id  # recorded on the call, not lost
        assert agent.state.closed_reason == "registered"
        assert "Užregistravau" in say and "leisti" not in say  # a fact, not a request
        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "dingo vakar" in details and "audra" in details  # anamnesis rides along


class TestTicketDialogue:
    """2026-08-04: every registration first collects the contact number (ALWAYS
    asked, never assumed from caller-ID/DB) and when to call — then registers with
    the contacts on the ticket."""

    def _agent_at_consent(self, monkeypatch):
        import os

        from agent.react_agent import ReactAgent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.caller_name = "Andrius"
        agent.state.caller_relation = "holder"
        agent.state.anamnesis_when = "vakar"
        agent.state.hypothesis = {
            "cause": "no_mac_observed",
            "status": "testing",
            "because": ["linijoje nematomas įrenginys"],
        }
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "escalate", "asked": True}
        return agent

    def test_consent_starts_dialogue_not_immediate_ticket(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent._walk_resolution("gerai, tinka")
        assert agent.state.ticket_id is None  # not yet — contacts first
        assert agent._ticket_stage == "phone"
        assert "Kokiu telefono numeriu" in agent._identification_scripted_reply("gerai, tinka")

    def test_full_dialogue_lands_contacts_on_ticket(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)  # asks the phone question
        # Q1 answer: "tiks šis" -> the number they call from.
        agent._pre_turn_guards("Taip, tiks šis numeris")
        assert agent.state.contact_phone == "+37060012353"
        assert agent._ticket_stage == "hours"
        agent._identification_scripted_reply("Taip, tiks šis numeris")  # asks hours
        # Q2 answer -> hours; the scripted turn then registers + closes.
        agent._pre_turn_guards("Po penkių vakare")
        assert agent._ticket_stage == "done"
        reply = agent._identification_scripted_reply("Po penkių vakare")
        assert "Užregistravau" in reply
        assert agent.state.ticket_id and agent.state.case_closed
        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "Andrius (holder), tel. +37060012353" in details
        assert "skambinti: Po penkių vakare" in details

    def test_dictated_number_captured(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)
        agent._pre_turn_guards("Geriau skambinkit 8 612 34 567")
        assert agent.state.contact_phone == "861234567"

    def test_farewell_mid_dialogue_registers_with_defaults(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._pre_turn_guards("viso gero")  # done talking — defaults kick in
        assert agent._ticket_stage == "done"
        reply = agent._identification_scripted_reply("viso gero")
        assert "Užregistravau" in reply
        assert agent.state.contact_phone == "+37060012353"
        assert agent.state.contact_hours == "bet kada"
        assert agent.state.ticket_id

    def test_intro_announces_cause_once(self, db_connection, monkeypatch):
        # The FIRST stage reply carries "Registruoju gedimą — {priežastis}"; a
        # re-ask does not repeat the intro.
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        first = agent._identification_scripted_reply(None)
        assert "Registruoju gedimą" in first and "maršrutizatorius" in first
        assert "Kokiu telefono numeriu" in first
        again = agent._ticket_stage_reply()
        assert "Registruoju gedimą" not in again  # intro said once

    def test_question_mid_dialogue_goes_to_llm_and_stage_holds(self, db_connection, monkeypatch):
        # "Bet kada galima skambinti?" is the caller ASKING — live it was captured
        # verbatim as the HOURS answer and landed on the ticket. It must divert to
        # the LLM (scripted None) and the stage must not advance.
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)
        agent._pre_turn_guards("taip, tiks šis")
        assert agent._ticket_stage == "hours"
        agent._identification_scripted_reply("taip, tiks šis")
        agent._pre_turn_guards("Tu sakė, užregistravai jau. Bet kada galima skambinti?")
        assert agent._ticket_stage == "hours"  # held, not captured
        assert agent.state.contact_hours is None
        assert agent._identification_scripted_reply("Bet kada galima skambinti?") is None
        facts = agent._state_facts_block()
        assert facts and "TIKETO DIALOGAS" in facts and "kada patogiausia" in facts
        # A plain answer next turn still lands.
        agent._ticket_offscript = False
        agent._pre_turn_guards("bet kada")
        assert agent.state.contact_hours == "bet kada"

    def test_done_announce_repeats_number_and_hours(self, db_connection, monkeypatch):
        # "Kokiu numeriu?" was asked twice live and got a goodbye — the announce
        # now repeats the number + hours so the question never arises.
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        reply = _complete_ticket_dialogue(agent)
        assert "+370 600 12353" in reply
        assert "bet kada" in reply

    def test_garbled_yes_and_stt_punctuation_stay_off_the_ticket(self, db_connection, monkeypatch):
        # Live: STT "T." (of "Taip") became tel. "T." and "Bet kada?" kept the "?"
        # on the ticket and in the announce.
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)
        agent._pre_turn_guards("T.")
        assert agent.state.contact_phone == "+37060012353"  # backchannel yes -> caller-ID
        agent._identification_scripted_reply("T.")
        agent._pre_turn_guards("Bet kada?")
        assert agent.state.contact_hours == "Bet kada"
        reply = agent._identification_scripted_reply("Bet kada?")
        assert "skambinti galima bet kada." in reply

    def test_trigger_utterance_not_swallowed_as_phone(self, db_connection, monkeypatch):
        # Live 2026-08-05: escalate fired mid-turn and the SAME utterance
        # ("Neturi kompiutera") was captured as the phone number, question
        # never asked. Answers count only after the question was asked.
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._pre_turn_guards("Neturi kompiutera")  # same-turn trigger phrase
        assert agent.state.contact_phone is None
        assert agent._ticket_stage == "phone"  # still waiting for its question
        first = agent._identification_scripted_reply("Neturi kompiutera")
        assert "Kokiu telefono numeriu" in first  # the question goes out now

    def test_garbage_phone_answer_reasks_then_defaults(self, db_connection, monkeypatch):
        # Live: "Neturi kompiutera" landed as tel. on the ticket. Now: one
        # scripted retry; a second unclear answer defaults to caller-ID.
        from agent.identification import phrase

        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)  # phone asked
        agent._pre_turn_guards("Kurs komentai")  # STT garbage
        assert agent.state.contact_phone is None
        reply = agent._identification_scripted_reply("Kurs komentai")
        assert reply == phrase("ticket_phone_retry")
        agent._pre_turn_guards("Visai nesuprantu ko klausiat")  # second garbage
        assert agent.state.contact_phone == "+37060012353"  # caller-ID default
        assert agent._ticket_stage == "hours"

    def test_garbage_hours_answer_reasks_then_defaults(self, db_connection, monkeypatch):
        # Live: "Kurs komentai" became "skambinti galima kurs komentai".
        from agent.identification import phrase

        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)
        agent._pre_turn_guards("taip, tiks šis")
        agent._identification_scripted_reply("taip, tiks šis")  # hours asked
        agent._pre_turn_guards("Kurs komentai")
        assert agent.state.contact_hours is None
        reply = agent._identification_scripted_reply("Kurs komentai")
        assert reply == phrase("ticket_hours_retry")
        agent._pre_turn_guards("Nu nezinau visai")  # second garbage -> default
        assert agent.state.contact_hours == "bet kada"
        assert agent._ticket_stage == "done"

    def test_first_fix_deferral_is_transition_and_offer(self, db_connection, monkeypatch):
        # Live: solver jumped to bind-speak ("pririšiu įrenginį") with no
        # transition — caller asked "Apie kokį kompiuterį kalbat?". The FIRST
        # deferral now announces the dead router and OFFERS the bridge.
        agent = self._agent_at_consent(monkeypatch)
        monkeypatch.setattr(
            "agent.react_agent.execute_tool",
            lambda name, args: json.dumps({"verdict": {"reason": "no_mac_observed"}}),
        )
        first = agent._drive_propose_fix("", "nedega lemputės")
        assert "routeris sugedęs" in first and "Ar turite kompiuterį" in first
        second = agent._drive_propose_fix("", "dar nieko nedariau")
        assert "pasakykite" in second  # the short wait line afterwards

    def test_plugged_into_computer_runs_bind_path_not_solver(self, db_connection, monkeypatch):
        # Eval S4: "Įkišau į kompiuterį" got yet another solver disambiguate and
        # the bind never ran. The plug-in report is ENGINE territory now — it
        # routes to _drive_propose_fix (whose own discipline still requires the
        # device to actually be visible before any bind).
        import os

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution["step"] = "dr_offer_bridge"
        called = {}

        def fake_propose(say, user_input):
            called["ran"] = True
            return "Pririšu įrenginį."

        monkeypatch.setattr(agent, "_drive_propose_fix", fake_propose)
        reply = agent.solver_drive_turn("Įkišau į kompiuterį")
        assert called.get("ran") is True
        assert reply == "Pririšu įrenginį."

    def test_tik_kompiuteri_is_not_a_no_device_answer(self, db_connection, monkeypatch):
        # "Neturiu kito routerio, tik kompiuterį" after the bridge offer must
        # NOT escalate — the caller HAS a computer (eval S4 regression).
        import os

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar turite kompiuterį, kad paleistume internetą?"}
        )
        agent._drive_disabled = True  # isolate: no solver LLM call
        reply = agent.solver_drive_turn("Neturiu kito routerio, tik kompiuterį")
        assert agent._ticket_stage is None  # no escalation fired
        # (evidence drive may still ask its next question — that is fine)

    def test_no_device_after_bridge_offer_escalates_deterministically(
        self, db_connection, monkeypatch
    ):
        # Live 2026-08-05: "Neturiu." after "Ar turite kompiuterį?" sent the
        # solver into a 6x disambiguate streak and a walker rewind. The answer
        # is ENGINE territory now: escalate the same turn, no solver involved.
        import os

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution["step"] = "dr_offer_bridge"
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "Panašu, kad routeris sugedęs. Ar turite kompiuterį, kad galėtume "
                    "laikinai paleisti internetą per jį?"
                ),
            }
        )
        reply = agent.solver_drive_turn("Neturiu, internetą naudoju tik telefonu.")
        assert reply is not None and "Kokiu telefono numeriu" in reply
        assert agent._ticket_stage == "phone"

    def test_registration_claim_without_ticket_starts_dialogue(self, db_connection, monkeypatch):
        # Live 2026-08-05: narrator said "Užregistravau gedimą…", ticket_id None,
        # caller hung up trusting it. The claim now pulls the real dialogue in.
        agent = self._agent_at_consent(monkeypatch)
        extra = agent._registration_claim_guard(
            "Supratau. Užregistravau gedimą, kolegos susisieks su jumis."
        )
        assert extra and "Kokiu telefono numeriu" in extra
        assert agent._ticket_stage == "phone"
        # Honest replies pass untouched.
        agent2 = self._agent_at_consent(monkeypatch)
        assert agent2._registration_claim_guard("Patikrinkime lemputes.") is None

    def test_hangup_mid_strategy_registers_safety_ticket(self, db_connection, monkeypatch):
        # Live 2026-08-05: the call ended via the UI button mid-strategy — no
        # ticket, despite a promised registration. end_session now registers
        # from state with the interruption on the record.
        agent = self._agent_at_consent(monkeypatch)
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket_id
        assert agent.state.closed_reason == "registered"
        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "Pokalbis nutrūko" in details
        assert "+37060012353" in details  # caller-ID default contact

    def test_hangup_after_resolved_call_registers_nothing(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent.state.case_closed = True
        agent.state.closed_reason = "resolved"
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket_id is None

    def test_hangup_net_skips_when_line_is_healthy(self, db_connection, monkeypatch):
        # Live 2026-08-06 (TKT00D19E54): the caller confirmed "veikia!" and hung
        # up before the goodbye — the net registered a technician for a HEALTHY
        # line. The line's current truth now decides: fresh diagnose healthy ->
        # no ticket, closed as resolved.
        agent = self._agent_at_consent(monkeypatch)
        monkeypatch.setattr(
            "agent.react_agent.execute_tool",
            lambda name, args: json.dumps({"verdict": {"reason": "healthy_to_router"}}),
        )
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket_id is None
        assert agent.state.closed_reason == "resolved"

    def test_hangup_net_skips_on_recorded_fix(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution["telemetry_fixed"] = True
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket_id is None
        assert agent.state.closed_reason == "resolved"

    def test_hangup_net_still_registers_when_fault_persists(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        # _agent_at_consent uses CUST009 whose seeded line still shows no_mac —
        # the real diagnose read confirms the fault persists -> ticket.
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket_id
        assert agent.state.closed_reason == "registered"

    def test_explicit_refusal_cancels_without_ticket(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        # Cancelling is a one-way door (2026-08-11): the first refusal gets ONE
        # confirm question; only the confirmed refusal cancels and closes.
        agent._pre_turn_guards("ne, nereikia registruoti nieko")
        assert agent._ticket_stage == "phone"
        assert "tikrai nereikia" in agent._ticket_stage_reply()
        agent._pre_turn_guards("nereikia")
        assert agent._ticket_stage == "cancelled"
        reply = agent._identification_scripted_reply("nereikia")
        assert "neregistruoju" in reply
        assert agent.state.ticket_id is None
        assert agent.state.case_closed and agent.state.closed_reason == "declined"

    def test_escalate_arrival_starts_dialogue_even_with_consent_step(
        self, db_connection, monkeypatch
    ):
        # Live 2026-08-04: arrival at a consent ESCALATE was narrated by the LLM
        # ("užregistravau…" before anything happened). Arrival now begins the
        # dialogue deterministically the same turn, consent step or not.
        agent = self._agent_at_consent(monkeypatch)
        assert agent.ensure_action_done() is True
        assert agent._ticket_stage == "phone"
