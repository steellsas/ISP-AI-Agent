import pytest

from tests.tool_fakes import install_fake_tools

"""
Tests for agent logic (without real LLM calls where possible).

These tests verify the engine's tool handling, tool descriptions and basic
logic. The LLM is mocked so no network/API key is needed.
Run: pytest tests/test_agent.py -v
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from agent.graph_v2.state import TicketContext


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


class TestAgentSystemPrompt:
    """Tests for agent system prompt."""

    def test_system_prompt_contains_tools(self):
        """System prompt should include tool descriptions."""
        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        assert "find_customer" in agent.system_prompt
        assert "search_knowledge" in agent.system_prompt
        assert "check_network_status" in agent.system_prompt


class TestAgentSystemPromptPhone:
    """Tests for agent state management."""

    def test_agent_phone_in_system_prompt(self):
        """Caller phone should be in system prompt."""
        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        assert "+37060012345" in agent.system_prompt


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
        from agent.narrator_flow import build_messages

        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        messages = build_messages(agent.state, agent.runtime)

        assert len(messages) >= 1
        assert messages[0]["role"] == "system"
        assert "find_customer" in messages[0]["content"]

    def test_build_messages_with_user_input(self):
        """Should add user input to messages."""
        from agent.narrator_flow import build_messages

        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        messages = build_messages(agent.state, agent.runtime, user_input="Labas")

        # Should have system + user message
        assert len(messages) >= 2
        assert messages[-1]["role"] == "user"
        assert "Labas" in messages[-1]["content"]


class TestHistoryWindow:
    """Tests for history pruning (windowing) and durable-fact injection."""

    def test_short_history_not_pruned(self):
        """History at or below the window is returned unchanged."""
        from agent.narrator_flow import prune_history

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.config.history_window_messages = 10
        agent.state.messages = [{"role": "user", "content": f"m{i}"} for i in range(5)]

        pruned = prune_history(agent.state, agent.runtime, agent.state.messages)

        assert pruned == agent.state.messages

    def test_window_zero_disables_pruning(self):
        """A window of 0 sends the full history."""
        from agent.narrator_flow import prune_history

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.config.history_window_messages = 0
        agent.state.messages = [{"role": "user", "content": f"m{i}"} for i in range(50)]

        pruned = prune_history(agent.state, agent.runtime, agent.state.messages)

        assert len(pruned) == 50

    def test_long_history_pruned_to_window(self):
        """A long, tool-free history is trimmed to exactly the window size."""
        from agent.narrator_flow import prune_history

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.config.history_window_messages = 6
        # 20 alternating user/assistant text messages (no tool exchanges)
        agent.state.messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(20)
        ]

        pruned = prune_history(agent.state, agent.runtime, agent.state.messages)

        assert len(pruned) == 6
        assert pruned[-1]["content"] == "m19"

    def test_prune_never_starts_on_orphaned_tool(self):
        """
        If the window boundary lands on a tool result, it must expand left to
        include the assistant(tool_calls) that owns it — otherwise the chat API
        rejects the orphaned tool message.
        """
        from agent.narrator_flow import prune_history

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
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

        pruned = prune_history(agent.state, agent.runtime, agent.state.messages)

        # window=3 would start on a tool result (index 3); must back up to the
        # assistant that issued the tool_calls (index 2).
        assert pruned[0].get("role") == "assistant"
        assert pruned[0].get("tool_calls") is not None
        # No tool result may appear without its owning assistant before it.
        assert pruned[0]["role"] != "tool"

    def test_build_messages_injects_known_facts(self):
        """Resolved GraphState facts ride in a SEPARATE trailing system message,
        not concatenated into the (cacheable) system prompt."""
        from agent.narrator_flow import build_messages

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.state.identity.set_customer(
            customer_id="C123",
            name="Jonas Jonaitis",
            address="Vilniaus g. 1, Vilnius",
        )

        messages = build_messages(agent.state, agent.runtime, user_input="Labas")

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
        from agent.narrator_flow import build_messages, state_facts_block

        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        facts = state_facts_block(agent.state, agent.runtime)
        assert facts is not None and "PROBLEMA DAR NEPASAKYTA" in facts
        messages = build_messages(agent.state, agent.runtime)
        assert messages[0]["content"] == agent.system_prompt

    def test_facts_block_surfaces_heard_address(self):
        """NLU-prefilled slots are surfaced so the model passes them to
        resolve_address instead of re-extracting garbled text (R5)."""
        from agent.narrator_flow import state_facts_block
        from agent.slots import SlotStatus

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.state.identity.profile.street.propose("Aušros g.", 0.8, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("8", 0.8, SlotStatus.HEARD)

        facts = state_facts_block(agent.state, agent.runtime)
        assert "HEARD ADDRESS" in facts
        assert "street=Aušros g." in facts
        assert "house=8" in facts

    def test_heard_address_hidden_once_identified(self):
        """Once identified the heard-address hint is dropped (already known)."""
        from agent.narrator_flow import state_facts_block
        from agent.slots import SlotStatus

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.state.identity.profile.street.propose("Aušros g.", 0.8, SlotStatus.HEARD)
        agent.state.identity.customer_id = "CUST110"

        facts = state_facts_block(agent.state, agent.runtime)
        assert "HEARD ADDRESS" not in (facts or "")

    def test_diagnosis_captured_and_surfaced(self, db_connection):
        """diagnose_connection findings become durable case state (Pillar A1)."""
        import json

        from agent.narrator_flow import state_facts_block, update_state_from_observation
        from agent.tools import diagnose_connection

        from tests.calls import make_agent

        agent = make_agent("+37060020105")
        obs = json.dumps(diagnose_connection("CUST105"))  # S5a -> B6 foreign_mac
        update_state_from_observation(agent.state, agent.runtime, "diagnose_connection", obs)

        assert agent.state.diagnosis.verdicts["network"]["group"] == "B6"
        assert agent.state.diagnosis.verdicts["network"]["reason"] == "foreign_mac"

        facts = state_facts_block(agent.state, agent.runtime)
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
        from tests.calls import make_agent

        agent = make_agent("+37060020102")
        agent.state.identity.customer_id = "CUST102"
        agent.state.diagnosis.verdicts["network"] = {"group": "B2", "reason": "active_outage"}
        agent.state.diagnosis.outage_reported = True
        agent.state.resolution.procedure = None  # inform mode: no strategy to walk
        return agent

    def test_farewell_closes_outage_call(self, db_connection):
        from agent.closing_flow import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "Ačiū, viso gero, sudie")
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "outage"
        assert agent.state.closing.is_complete is True

    def test_no_farewell_keeps_call_open(self, db_connection):
        from agent.closing_flow import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "O kada tiksliai sutvarkysite?")
        assert agent.state.closing.case_closed is False

    def test_active_strategy_never_closed_here(self, db_connection):
        """A live troubleshooting strategy belongs to the walker — a mid-flow 'ne'
        must not end the call."""
        from agent.closing_flow import maybe_close_inform

        agent = self._informed_agent()
        agent.state.diagnosis.outage_reported = False
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "foreign_mac"}
        agent.state.resolution.procedure = {"verdict": "foreign_mac", "step": "confirm_change"}
        maybe_close_inform(agent.state, agent.runtime, "ne")
        assert agent.state.closing.case_closed is False


def _complete_ticket_dialogue(agent):
    """Walk the 2-question contact dialogue (2026-08-04) to the registration.
    Each stage question must be ASKED before its answer counts (2026-08-05)."""
    from agent.identification_flow import identification_scripted_reply
    from agent.perception_flow import pre_turn_guards

    identification_scripted_reply(agent.state, agent.runtime, None)  # intro + phone question
    pre_turn_guards(agent.state, agent.runtime, "taip, tiks šis")
    identification_scripted_reply(agent.state, agent.runtime, "taip, tiks šis")  # hours question
    pre_turn_guards(agent.state, agent.runtime, "bet kada")
    return identification_scripted_reply(agent.state, agent.runtime, "bet kada")


class TestEscalateOutcome:
    """Phase 3.11 B: the ESCALATE step is a deterministic OUTCOME — the ENGINE
    registers the ticket from state on consent; the model no longer calls
    create_ticket. Classifier off -> the keyword consent reader drives routing."""

    def _agent_on_escalate(self, monkeypatch):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "no_mac_observed"}
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "escalate",
            "asked": True,  # the consent question was posed last turn
        }
        return agent

    def test_consent_registers_ticket_and_closes(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_on_escalate(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "gerai, tinka")
        assert agent.state.ticket.stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
        assert agent.state.ticket.ticket_id  # engine-created, from state
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "registered"

    def test_decline_closes_without_ticket(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_on_escalate(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "ne, nenoriu, ačiū")
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "declined"

    def test_unclear_holds_the_step(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_on_escalate(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "hmm palaukite sekundėlę")
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.case_closed is False  # re-ask, don't register on a garble

    def test_not_asked_yet_never_advances(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_on_escalate(monkeypatch)
        agent.state.resolution.procedure["asked"] = False
        walk_resolution(
            agent.state, agent.runtime, "gerai, tinka"
        )  # "taip" to something else entirely
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.case_closed is False


class TestHearingAgent:
    """2026-08-11 live fix: a barge-in-truncated "Ne." (meant "ne, nedega…") was
    read by the STALE dr_intro yes/no as "won't check" → escalate → ticket →
    dead call. Ownership: an open evidence question owns the reply; a bare
    negation CLARIFIES instead of driving one-way doors (escalate, ticket
    cancel); first evidence asks explain WHY (kodel from faults.yaml)."""

    def _agent(self, monkeypatch, step="dr_intro", asked=True):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "no_mac_observed"}
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
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
        from agent.walker_flow import walk_resolution

        agent = self._agent(monkeypatch)
        agent.state.diagnosis.pending_evidence_key = "power_cable"
        agent.state.diagnosis.evidence_ask_counts["power_cable"] = 1
        walk_resolution(agent.state, agent.runtime, "Ne.")  # the fatal live turn
        assert agent.state.resolution.procedure["step"] == "dr_intro"  # held, not escalate
        assert agent.state.ticket.stage is None

    def test_open_question_negation_gets_fault_file_clarify(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply

        agent = self._agent(monkeypatch)
        agent.state.diagnosis.pending_evidence_key = "power_cable"
        agent.state.diagnosis.evidence_ask_counts["power_cable"] = 1
        reply = identification_scripted_reply(agent.state, agent.runtime, "Ne.")
        assert reply is not None and "neįkištas" in reply  # patikslinimas wording

    def test_drive_negation_clarify_replaces_reask(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact
        from agent.evidence_drive import evidence_drive

        agent = self._agent(monkeypatch)
        set_fact(agent.state.diagnosis.evidence, "ivykiai", "nebuvo", CLIENT, 0)
        set_fact(agent.state.diagnosis.evidence, "device_present", "rado", CLIENT, 1)
        set_fact(agent.state.diagnosis.evidence, "lights", "nedega", CLIENT, 2)
        agent.state.diagnosis.pending_evidence_key = "power_cable"
        agent.state.diagnosis.evidence_ask_counts["power_cable"] = 1
        reply = evidence_drive(agent.state, agent.runtime, "Ne.")
        assert reply is not None and "neįkištas" in reply

    def test_kodel_rides_on_first_evidence_ask(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact
        from agent.evidence_drive import evidence_drive

        agent = self._agent(monkeypatch)
        set_fact(agent.state.diagnosis.evidence, "ivykiai", "nebuvo", CLIENT, 0)
        set_fact(agent.state.diagnosis.evidence, "device_present", "rado", CLIENT, 1)
        reply = evidence_drive(agent.state, agent.runtime, "radau")
        assert reply is not None and "lemputė" in reply
        assert "maitinimą" in reply  # the kodel sentence

    @pytest.mark.usefixtures("walker_driven")
    def test_bare_ne_to_escalate_clarifies_once_then_escalates(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        # P-C (2026-09-10): plikas "Ne." dr_intro žingsnyje dabar veda į
        # NAMŲ DARBO sutikimą (ne tiesiai į escalate) — vienpusės durys
        # persikėlė ten; "ne + registruokite" iš homework -> escalate.
        agent = self._agent(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "Ne.")
        assert agent.state.resolution.procedure["step"] == "dr_homework"
        agent.state.resolution.procedure["asked"] = True
        walk_resolution(agent.state, agent.runtime, "Ne, registruokite meistrą")
        assert agent.state.resolution.procedure["step"] == "escalate"

    def test_rich_refusal_still_escalates_directly(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "Nieko nedarysiu, įregistruokit gedimą")
        assert agent.state.ticket.stage == "phone"  # refuse/demand path untouched

    def test_ticket_cancel_needs_one_confirm(self, db_connection, monkeypatch):
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import ticket_stage_reply

        agent = self._agent(monkeypatch, step="escalate")
        agent.state.ticket.stage = "phone"
        agent.state.ticket.context = TicketContext(phone_asked=True, intro_done=True)
        pre_turn_guards(agent.state, agent.runtime, "Neregistruokite nieko")
        assert agent.state.ticket.stage == "phone"  # not cancelled yet
        reply = ticket_stage_reply(agent.state, agent.runtime)
        assert "tikrai nereikia" in reply  # the confirm question went out
        pre_turn_guards(agent.state, agent.runtime, "nereikia")
        assert agent.state.ticket.stage == "cancelled"  # confirmed refusal cancels

    def test_ticket_cancel_confirm_can_resume(self, db_connection, monkeypatch):
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import ticket_stage_reply

        agent = self._agent(monkeypatch, step="escalate")
        agent.state.ticket.stage = "phone"
        agent.state.ticket.context = TicketContext(phone_asked=True, intro_done=True)
        pre_turn_guards(agent.state, agent.runtime, "Neregistruokite nieko")
        ticket_stage_reply(agent.state, agent.runtime)  # confirm question goes out
        pre_turn_guards(agent.state, agent.runtime, "gerai, registruokite vis dėlto")
        assert agent.state.ticket.stage == "phone"  # resumed, not cancelled
        assert "numeris" in ticket_stage_reply(agent.state, agent.runtime)  # stage re-asks

    # --- round 2 (live 2026-08-11, call 2) ------------------------------------

    def test_end_confirm_answer_never_routes_the_walker(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        # "Iki šau." (STT of "Įkišau") triggered confirm-end; the answer "Ne,
        # nenoriu" (= don't END) then advanced stale dr_intro -> escalate ->
        # ticket. The walker holds while the confirm-end answer is unread.
        agent = self._agent(monkeypatch)
        agent.state.dialog.end_confirm_pending = True
        walk_resolution(agent.state, agent.runtime, "Ne, nenoriu.")
        assert agent.state.resolution.procedure["step"] == "dr_intro"
        assert agent.state.ticket.stage is None

    def test_ticket_refusal_with_solving_content_returns_to_fix(self, db_connection, monkeypatch):
        from agent.perception_flow import pre_turn_guards

        agent = self._agent(monkeypatch, step="escalate")
        agent.state.ticket.stage = "phone"
        agent.state.ticket.context = TicketContext(phone_asked=True, intro_done=True)
        pre_turn_guards(agent.state, agent.runtime, "Neregistruokite, pajunkim tą kompiuterį")
        assert agent.state.ticket.stage is None  # dialogue dropped…
        assert agent.state.closing.case_closed is False  # …but the call stays OPEN
        assert agent.state.ticket.resume_fix_note is True  # narrator returns to the fix

    def test_cancel_confirm_answer_with_solving_content_returns_to_fix(
        self, db_connection, monkeypatch
    ):
        from agent.perception_flow import pre_turn_guards

        agent = self._agent(monkeypatch, step="escalate")
        agent.state.ticket.stage = "phone"
        agent.state.ticket.context = TicketContext(
            phone_asked=True, intro_done=True, cancel_confirm_asked=True, cancel_confirm_out=True
        )
        pre_turn_guards(
            agent.state, agent.runtime, "Ne, tai mes pajunkim tą kompiuterį. Aš jungiu kabelį."
        )
        assert agent.state.ticket.stage is None
        assert agent.state.closing.case_closed is False
        assert agent.state.ticket.resume_fix_note is True

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
        from agent.walker_flow import walk_resolution

        # dr_intro presented ~15 turns earlier consumed "Dar interneto nėra."
        # as its own "no" -> escalate -> ticket (three live calls in a row).
        agent = self._agent(monkeypatch)
        agent.state.resolution.procedure["asked_at"] = 0
        agent.state.messages.extend({"role": "user", "content": f"turn {i}"} for i in range(8))
        walk_resolution(agent.state, agent.runtime, "Ne.")
        assert agent.state.resolution.procedure["step"] == "dr_intro"  # held — question too old
        assert agent.state.ticket.stage is None

    def test_fresh_step_question_still_routes(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent(monkeypatch)
        agent.state.resolution.procedure["asked_at"] = len(agent.state.messages)
        walk_resolution(agent.state, agent.runtime, "nieko nedarysiu, įregistruokit gedimą")
        assert agent.state.ticket.stage == "phone"  # refuse/demand path unaffected

    # --- round 4 (live 2026-08-11, call 4: bind never ran) --------------------

    def test_plug_report_reads_context_not_one_sentence(self, db_connection, monkeypatch):
        from agent.solver_flow import plug_report

        agent = self._agent(monkeypatch)
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Dabar įkiškite tą kabelį į kompiuterio tinklo lizdą — "
                "pasakykite, kai padarysite.",
            }
        )
        assert plug_report(agent.state, agent.runtime, "Ikišau, ikišau, laukiu internetą.") is True
        assert (
            plug_report(agent.state, agent.runtime, "Taip, jis įkištas iki galo.") is True
        )  # passive
        assert (
            plug_report(agent.state, agent.runtime, "Pririškite tada.") is True
        )  # explicit bind ask
        assert (
            plug_report(agent.state, agent.runtime, "dar neprijungiau, sekundėlę") is False
        )  # negation
        # The SAME words during the power-cable phase are NOT a bind report.
        agent.state.messages[-1] = {
            "role": "assistant",
            "content": "Patikrinkite, ar maitinimo laidas gerai įkištas į rozetę.",
        }
        assert plug_report(agent.state, agent.runtime, "Įkišau gerai.") is False

    def test_plug_report_memory_unlocks_the_bind_gate(self, db_connection, monkeypatch):
        from agent.solver_flow import drive_propose_fix

        # "Įkišau, laukiu" three turns ago — the gate demanded the verb in THIS
        # turn's utterance and kept repeating "Kai prijungsite…" (live).
        agent = self._agent(monkeypatch)
        agent.state.resolution.bridge_plug_reported = True
        agent.state.resolution.bridge_offered = True
        reply = drive_propose_fix(agent.state, agent.runtime, "", "taip, viskas padaryta, laukiu")
        assert "Kai prijungsite" not in reply  # no more deferral on wording
        assert (
            agent.state.resolution.bridge_bound or "nematome" in reply
        )  # bind ran (or line check)

    def test_bailout_lands_on_declared_solution_step(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(monkeypatch)
        for k, v in (
            ("device_present", "rado"),
            ("lights", "nedega"),
            ("power_cable", "įkištas"),
            ("outlet_works", "bandyta"),
            ("has_computer", "yes"),
        ):
            set_fact(agent.state.diagnosis.evidence, k, v, CLIENT, 1)
        agent.state.identity.caller_name = "Andrius"
        agent.state.diagnosis.facts_recap_state = "done"
        agent.state.diagnosis.findings_announced = True
        agent.state.resolution.bridge_offered = True
        agent.state.resolution.drive_repeats = 2  # distrust streak observed
        assert (
            solver_drive_turn(agent.state, agent.runtime, "prijungiau, laukiu") is None
        )  # walker resumes…
        assert agent.state.resolution.procedure["step"] == "dr_pick_cable"  # …AT the bridge

    # --- round 5 (2026-08-12): bridge-failure ladder ---------------------------

    def test_bridge_fail_ladder_lan_check_then_technician(self, db_connection, monkeypatch):
        from agent.perception_flow import ingest_client_evidence
        from agent.solver_flow import drive_propose_fix

        # Plug reported, telemetry never shows the device (no simulation):
        # (1) say the line sees nothing + cable re-check, (2) the LAN question,
        # (3) incoming-cable note + technician, attempt on the ticket.
        agent = self._agent(monkeypatch)
        agent.state.identity.caller_name = "Andrius"
        agent.state.resolution.bridge_plug_reported = True
        agent.state.resolution.bridge_offered = True
        r1 = drive_propose_fix(agent.state, agent.runtime, "", "pajungiau kabelį")
        assert "nematome jūsų kompiuterio" in r1
        r2 = drive_propose_fix(agent.state, agent.runtime, "", "vis dar nieko")
        assert "LAN" in r2  # the computer's network card, not the router
        assert agent.state.diagnosis.pending_evidence_key == "lan_active"
        ingest_client_evidence(agent.state, agent.runtime, "Nerodo nieko, neaktyvus")
        assert agent.state.diagnosis.evidence["lan_active"]["value"] == "neaktyvus"
        r3 = drive_propose_fix(agent.state, agent.runtime, "", "ir dabar nieko")
        assert "kabeliu" in r3  # the possible incoming-cable problem is NAMED
        assert "Ar tiks numeris" in r3  # technician registration begins
        assert "NEPAVYKO" in (agent.state.ticket.bridge_fail_note or "")
        _complete_ticket_dialogue(agent)
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "NEPAVYKO" in details and "neaktyvus" in details

    # --- round 6 (live 2026-08-12): dead ends resolve, success is heard -------

    def test_unconfirmed_bailout_goes_to_escalate_not_intro(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(monkeypatch)
        agent.state.identity.caller_name = "Andrius"
        for k, v in (
            ("ivykiai", "nebuvo"),
            ("device_present", "rado"),
            ("lights", "nedega"),
            ("power_cable", "neaišku"),  # gave up — hypothesis unconfirmable
        ):
            set_fact(agent.state.diagnosis.evidence, k, v, CLIENT, 1)
        agent.state.diagnosis.revived_evidence_keys = ["power_cable"]  # revival already spent
        agent.state.resolution.drive_repeats = 2  # distrust streak observed
        assert solver_drive_turn(agent.state, agent.runtime, "nežinau ką daugiau daryti") is None
        assert agent.state.resolution.procedure["step"] == "escalate"  # honest endgame

    def test_bind_lands_walker_on_verify_and_hears_restored(self, db_connection, monkeypatch):
        # Tools are FAKED so the shared session DB is not mutated (a real bind
        # here flips CUST009 healthy and breaks later ordering-dependent tests).
        import json as _json

        from agent.solver_flow import drive_propose_fix
        from agent.walker_flow import walk_resolution

        agent = self._agent(monkeypatch)
        agent.state.resolution.bridge_plug_reported = True
        agent.state.resolution.bridge_offered = True
        calls = []

        def fake_execute(name, args):
            calls.append(name)
            if name == "diagnose_connection":
                reason = "foreign_mac" if "simulated" in calls else "no_mac_observed"
                return _json.dumps({"success": True, "verdict": {"reason": reason}})
            return _json.dumps({"success": True})

        install_fake_tools(monkeypatch, fake_execute)
        monkeypatch.setattr(
            "agent.executor_flow.simulate_bridge_connection",
            lambda state, rt: calls.append("simulated"),
        )
        monkeypatch.setattr("agent.narrator_flow.augment_tool_result", lambda state, rt, n, o: o)
        reply = drive_propose_fix(agent.state, agent.runtime, "", "įkišau į kompiuterį")
        assert "ririšau" in reply.lower() or "Pririšau" in reply  # the bind ran
        assert agent.state.resolution.procedure["step"] == "dr_verify"  # verify owns the next reply
        walk_resolution(agent.state, agent.runtime, "Jau atsistatė, veikia internetas!")
        assert agent.state.resolution.procedure["step"] == "dr_register_router"  # success HEARD

    def test_ticket_intro_after_working_bridge_states_the_success(self, db_connection, monkeypatch):
        from agent.ticket_flow import begin_ticket_dialogue, ticket_stage_reply

        # "Telefonu šio gedimo išspręsti nepavyks" right after the internet
        # CAME BACK read as a failure (live 2026-08-12) — the post-bridge
        # intro states the success and registers the router replacement.
        agent = self._agent(monkeypatch, step="escalate")
        agent.state.resolution.bridge_bound = True
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        intro = ticket_stage_reply(agent.state, agent.runtime)
        assert "veikia per kompiuterį" in intro
        assert "nepavyks" not in intro
        assert "Ar tiks numeris" in intro

    def test_lan_pending_answers(self):
        from agent.evidence import read_pending_answer

        assert read_pending_answer("lan_active", "Rodo, kad aktyvus") == "aktyvus"
        assert read_pending_answer("lan_active", "Nerodo nieko") == "neaktyvus"
        assert read_pending_answer("lan_active", "dega lemputė prie lizdo") == "aktyvus"

    def test_on_task_question_stays_with_the_flow(self, db_connection, monkeypatch):
        from agent.perception_flow import classify_side_topic

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
        assert (
            classify_side_topic(agent.state, agent.runtime, "Kur jungti tą kabelį į kompiuterį?")
            is False
        )
        # An off-task FAQ question still goes to the side node.
        assert classify_side_topic(agent.state, agent.runtime, "O kiek kainuos meistras?") is True


class TestAutoRegisterEscalate:
    """consent=False ESCALATE (dr_register_router): the registration is a necessity —
    the engine registers ON ARRIVAL and closes; no consent question, no misread."""

    def test_arrival_registers_and_closes(self, db_connection, monkeypatch):
        import os

        from agent.walker_flow import ensure_action_done

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_register_router",
        }

        ran = ensure_action_done(agent.state, agent.runtime)

        assert ran is True
        assert agent.state.ticket.stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
        assert agent.state.ticket.ticket_id
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "registered"

    def test_lauksiu_skambucio_is_consent_not_decline(self):
        from agent.resolution import detect_ticket_consent

        assert detect_ticket_consent("Lauksiu skambučio, ačiū") == "yes"

    def test_farewell_stt_garbles_close(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Neturiu, neturiu, visą gerą") is True
        assert detect_farewell("visa gera, ačiū") is True


@pytest.mark.usefixtures("walker_driven")
class TestRestoredPreAnswer:
    """A clear 'atsirado / veikia' fused with the goodbye pre-answers the restored
    CONFIRM before it was asked — the resolve gets RECORDED instead of the call dying
    unclosed on the hangup (observed live: resolved Wi-Fi call left outcome=None)."""

    def test_restored_yes_advances_unasked_verify(self, db_connection, monkeypatch):
        import os

        from agent.walker_flow import walk_resolution

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060020109")
        agent.state.identity.customer_id = "CUST109"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.verdicts["network"] = {"group": "B7", "reason": "healthy_to_router"}
        agent.state.diagnosis.hypothesis = {"cause": "healthy_to_router", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "healthy_to_router",
            "step": "cs_verify_dev",
            "asked": False,  # the question was never posed — caller pre-answered
        }

        walk_resolution(
            agent.state, agent.runtime, "Įjungta, yra internetas, ačiū, atsirado. Viso gero."
        )

        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "resolved"


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
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import pre_turn_guards

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 3?"}
        )
        pre_turn_guards(agent.state, agent.runtime, "Taip, nebija")
        assert agent.state.turn.address_confirm_note is not None  # veto: do not resolve the offer
        facts = state_facts_block(agent.state, agent.runtime)
        assert facts and "NEPATVIRTINTAS" in facts

    def test_correction_asks_confirmation_then_reopens(self, db_connection):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards

        # Etalonas №3 (2026-09-03): a correction no longer reopens INSTANTLY —
        # one confirmation question first; a "taip" (or a named new address)
        # then drops the identity.
        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.identity.customer_address = "Šiauliai, Tilžės g. 60-3"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        pre_turn_guards(agent.state, agent.runtime, "Tai ne dėl to adresų skambinu")
        assert agent.state.identity.customer_id == "CUST101"  # NOT dropped yet
        assert agent.state.identity.reopen_confirm_utterance
        reply = identification_scripted_reply(
            agent.state, agent.runtime, "Tai ne dėl to adresų skambinu"
        )
        assert reply and "tikrai" in reply  # the confirmation question
        # A-2 (2026-09-07): the ANSWER is read in pre_turn_guards (the turn head,
        # before the solver/walker can consume it) — mirror the live sequence.
        pre_turn_guards(agent.state, agent.runtime, "Taip, dėl kito adreso")
        assert agent.state.identity.customer_id is None  # identity dropped after the yes
        assert agent.state.diagnosis.verdicts == {}  # per-account conclusions dropped
        assert agent.state.turn.reopen_note is True


class TestRefuseOrTicket:
    """A refusal / explicit ticket demand ends troubleshooting in a registration."""

    def _agent_mid_flow(self, monkeypatch, step="cable_check"):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060020105")
        agent.state.identity.customer_id = "CUST105"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.hypothesis = {"cause": "foreign_mac", "status": "testing"}
        agent.state.resolution.procedure = {"verdict": "foreign_mac", "step": step, "asked": True}
        return agent

    def test_demand_registers_immediately(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_mid_flow(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "Nieko nedarysiu, įregistruokit gedimą")
        assert agent.state.ticket.stage == "phone"  # contacts dialogue first (2026-08-04)
        _complete_ticket_dialogue(agent)
        assert agent.state.ticket.ticket_id
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "registered"

    def test_refuse_routes_to_escalate_consent(self, db_connection, monkeypatch):
        from agent.walker_flow import walk_resolution

        agent = self._agent_mid_flow(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "Aš nenamosiu")  # garbled refusal
        r = agent.state.resolution.procedure
        assert r["step"] == "escalate"  # polite consent question comes next
        assert agent.state.ticket.ticket_id is None  # not registered yet — clarify first
        assert r["escalate_reason"] == "caller_refused"


class TestAddressSpeech:
    def test_spoken_address_form(self):
        from agent.voice_pipeline import speech_text as n

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
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import pre_turn_guards

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent.state.identity.result_pending = True  # the caller question was posed last reply

        pre_turn_guards(agent.state, agent.runtime, "Ona, aš žmona sutartį sudariusio")

        assert agent.state.identity.caller_name == "Ona"  # the NAME, not the sentence
        assert agent.state.identity.caller_relation == "family"
        # The RESULT directive now renders (deferred news released this turn).
        facts = state_facts_block(agent.state, agent.runtime)
        assert facts and "REZULTATO PRISTATYMAS" in facts

    def test_relation_keywords(self):
        from agent.identification import detect_caller_relation

        assert detect_caller_relation("Jonas, taip, aš sutartį sudaręs") == "holder"
        assert detect_caller_relation("Petras, nuomininkas") == "tenant"
        assert detect_caller_relation("kaimynas, padedu senolei") == "helper"
        assert detect_caller_relation("mmm") == "unknown"

    def test_engine_resolves_dictated_correction(self, db_connection):
        from agent.identification_flow import prefill_slots_from_text
        from agent.perception_flow import pre_turn_guards

        from tests.calls import make_agent

        agent = make_agent("+37060020105")  # phone = 60-7 account
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 7?"}
        )
        prefill_slots_from_text(
            agent.state, agent.runtime, "Ne, skambinu dėl Tilžės gatvės 60 buto 3"
        )
        pre_turn_guards(agent.state, agent.runtime, "Ne, skambinu dėl Tilžės gatvės 60 buto 3")

        # The ENGINE committed the corrected identity and diagnosed silently.
        assert agent.state.identity.customer_id == "CUST101"
        assert agent.state.diagnosis.verdicts["network"]["reason"] == "billing_suspended"
        # The reply is steered by the identified-note (ladder: caller question next).
        assert (
            agent.state.turn.address_confirm_note
            and "IDENTIFIKUOTA" in agent.state.turn.address_confirm_note
        )
        assert agent.state.identity.result_pending is True

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

        from agent.walker_flow import walk_resolution

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_offer_bridge",
            "asked": True,
        }

        walk_resolution(
            agent.state, agent.runtime, "T."
        )  # was read as "yes, I have a computer" live
        assert agent.state.resolution.procedure["step"] == "dr_offer_bridge"  # held
        walk_resolution(agent.state, agent.runtime, "Mhm.")
        assert agent.state.resolution.procedure["step"] == "dr_offer_bridge"  # held

    def test_caller_intro_with_stt_question_mark_is_captured(self, db_connection):
        from agent.perception_flow import pre_turn_guards

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent.state.identity.result_pending = True

        pre_turn_guards(
            agent.state, agent.runtime, "Tomas? Ne, mano vardas Tomas, aš esu kaimynas."
        )
        assert agent.state.identity.caller_name is not None  # captured, not skipped as a question
        assert agent.state.identity.caller_relation == "helper"

    def test_inform_close_gated_until_news_told(self, db_connection):
        from agent.closing_flow import maybe_close_inform

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent.state.identity.result_pending = True  # ladder still open, news NOT delivered

        maybe_close_inform(agent.state, agent.runtime, "viso gero")
        assert agent.state.closing.case_closed is False  # must NOT hang up before informing

    def test_farewell_mid_strategy_confirms_then_registers(self, db_connection, monkeypatch):
        import os

        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "asked": True,
        }

        pre_turn_guards(agent.state, agent.runtime, "viso gero")  # mid-troubleshooting goodbye
        assert agent.state.dialog.end_confirm_pending is True
        assert agent.state.closing.case_closed is False  # clarify first, never hang up
        reply = identification_scripted_reply(agent.state, agent.runtime, "viso gero")
        assert reply and "tikrai norite baigti" in reply

        pre_turn_guards(
            agent.state, agent.runtime, "taip, baikim"
        )  # confirmed -> contacts, then registration
        assert agent.state.ticket.stage == "phone"
        _complete_ticket_dialogue(agent)
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "registered"
        assert agent.state.ticket.ticket_id

    def test_farewell_mid_strategy_declined_resumes(self, db_connection, monkeypatch):
        import os

        from agent.perception_flow import pre_turn_guards
        from agent.walker_flow import walk_resolution

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "asked": True,
        }

        pre_turn_guards(agent.state, agent.runtime, "viso gero")
        pre_turn_guards(agent.state, agent.runtime, "ne ne, tęskime")  # changed their mind
        assert agent.state.closing.case_closed is False
        assert agent.state.dialog.end_confirm_pending is False
        walk_resolution(
            agent.state, agent.runtime, "ne ne, tęskime"
        )  # held one turn, not misrouted
        assert agent.state.resolution.procedure["step"] == "dr_lights"


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
        from agent.walker_flow import open_hypothesis

        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.intake.anamnesis_when = "šiandien"
        agent.state.intake.anamnesis_trigger = "audra"
        open_hypothesis(agent.state, agent.runtime, "no_mac_observed")

        because = " ".join(agent.state.diagnosis.hypothesis["because"])
        assert "klientas sako" in because and "audra" in because

    def test_ticket_carries_anamnesis(self, db_connection, monkeypatch):
        import os

        from agent.walker_flow import ensure_action_done

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_when = "vakar"
        agent.state.intake.anamnesis_trigger = "audra"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_register_router",
        }

        ensure_action_done(agent.state, agent.runtime)  # consent-free: contacts dialogue on arrival
        _complete_ticket_dialogue(agent)

        assert agent.state.ticket.ticket_id
        import sqlite3

        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "Klientas: dingo vakar, po: audra" in details


class TestSideTopicNode:
    """2026-08-07: 'kiek kainuos?' was asked twice and ignored (the evidence
    drive has no question path); 'Aš skola kokia.' closed the call. Deviations
    now freeze the engine, answer from the FAQ and return to the anchor."""

    def _diagnosing(self, monkeypatch):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "asked": True,
        }
        agent.state.dialog.last_question = "Pažiūrėkite, ar ant routerio dega bent viena lemputė."
        return agent

    def test_question_freezes_engine_and_flags_side_topic(self, db_connection, monkeypatch):
        from agent.perception_flow import classify_side_topic
        from agent.solver_flow import solver_drive_turn
        from agent.walker_flow import advance_resolution

        agent = self._diagnosing(monkeypatch)
        assert classify_side_topic(agent.state, agent.runtime, "O kiek man tai kainuos?") is True
        assert (
            solver_drive_turn(agent.state, agent.runtime, "O kiek man tai kainuos?") is None
        )  # thinker yields
        advance_resolution(agent.state, agent.runtime, "O kiek man tai kainuos?")
        assert agent.state.resolution.procedure["step"] == "dr_lights"  # frozen, not advanced

    def test_side_facts_carry_faq_and_anchor(self, db_connection, monkeypatch):
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import classify_side_topic

        agent = self._diagnosing(monkeypatch)
        agent.state.dialog.last_heard = "O kiek man tai kainuos?"
        classify_side_topic(agent.state, agent.runtime, "O kiek man tai kainuos?")
        facts = state_facts_block(agent.state, agent.runtime)
        assert "NUKRYPIMAS" in facts
        assert "nieko nekainuoja" in facts  # faq.yaml hit rides in
        assert "dega bent viena lemputė" in facts  # the return anchor

    def test_unknown_topic_gets_not_my_area_directive(self, db_connection, monkeypatch):
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import classify_side_topic

        agent = self._diagnosing(monkeypatch)
        agent.state.dialog.last_heard = "O koks rytoj oras Šiauliuose?"
        classify_side_topic(agent.state, agent.runtime, "O koks rytoj oras Šiauliuose?")
        facts = state_facts_block(agent.state, agent.runtime)
        assert "ATSAKYMO NĖRA" in facts

    def test_third_deviation_is_scripted_frame(self, db_connection, monkeypatch):
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import classify_side_topic

        agent = self._diagnosing(monkeypatch)
        for q in ("O kiek kainuos?", "O koks oras?", "O kur jūsų ofisas?"):
            classify_side_topic(agent.state, agent.runtime, q)
        reply = identification_scripted_reply(agent.state, agent.runtime, "O kur jūsų ofisas?")
        assert reply == phrase(
            "identification.back_to_issue",
            inkaras="Pažiūrėkite, ar ant routerio dega bent viena lemputė.",
        )

    def test_third_deviation_with_confirmed_hypothesis_offers_choice(
        self, db_connection, monkeypatch
    ):
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import classify_side_topic, ingest_client_evidence

        agent = self._diagnosing(monkeypatch)
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        ingest_client_evidence(agent.state, agent.runtime, "Laidas įkištas, bandžiau kitą rozetę")
        for q in ("O kiek kainuos?", "O koks oras?", "O kur jūsų ofisas?"):
            classify_side_topic(agent.state, agent.runtime, q)
        reply = identification_scripted_reply(agent.state, agent.runtime, "O kur jūsų ofisas?")
        assert reply == phrase("identification.solve_or_ticket")

    def test_informative_interruption_is_not_a_deviation(self, db_connection, monkeypatch):
        from agent.perception_flow import classify_side_topic

        agent = self._diagnosing(monkeypatch)
        agent.state.dialog.side_topic_streak = 2
        assert (
            classify_side_topic(
                agent.state, agent.runtime, "Kur ta lemputė? Nedega nė viena lemputė"
            )
            is False
        )
        assert agent.state.dialog.side_topic_streak == 0  # productive turn resets the streak

    def test_refusal_and_farewell_yield_to_walker_policies(self, db_connection, monkeypatch):
        import os

        from agent.solver_flow import solver_drive_turn

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._diagnosing(monkeypatch)
        # "neturiu laiko" got a solver wait->close and NO ticket live — the
        # thinker must hand policy turns to the walker + guards.
        assert (
            solver_drive_turn(agent.state, agent.runtime, "Pala, aš nieko nedarysiu, neturiu laiko")
            is None
        )
        assert solver_drive_turn(agent.state, agent.runtime, "gerai, viso gero") is None

    def test_hours_scrubbed_of_inner_question_marks(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._diagnosing(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "taip, tiks šis")
        identification_scripted_reply(agent.state, agent.runtime, "taip, tiks šis")
        pre_turn_guards(agent.state, agent.runtime, "Bet kada? Bet kurio laiko?")
        assert agent.state.ticket.contact_hours == "Bet kada Bet kurio laiko"

    def test_checking_cue_spoken_on_identity_commit(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply

        agent = self._diagnosing(monkeypatch)
        agent.state.resolution.procedure = None
        agent.state.identity.customer_address = "Šiauliai, Vilniaus g. 29"
        agent.state.identity.just_identified = True
        agent.state.identity.result_pending = True
        reply = identification_scripted_reply(agent.state, agent.runtime, None)
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
        # Policy 2026-08-20 (Andrius): a bare "Ne." is an ANSWER — its
        # question owner clarifies; never a farewell.
        assert detect_farewell("Ne.") is False
        assert detect_farewell("Ne, ačiū") is True
        assert detect_farewell("viskas gerai") is True
        assert detect_farewell("viso gero") is True


class TestReviewGaps:
    """2026-08-07 architecture review fixes."""

    def test_reopen_clears_evidence_and_dialogue_state(self, db_connection, monkeypatch):
        # Stale-state bomb: after an address correction the OLD account's
        # telemetry facts (the verdict!) survived in the ledger.
        import os

        from agent.identification_flow import reopen_identification
        from agent.narrator_flow import update_state_from_observation
        from agent.perception_flow import ingest_client_evidence
        from agent.ticket_flow import begin_ticket_dialogue

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "asked": True,
        }
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "diagnose_connection",
            json.dumps({"verdict": {"reason": "no_mac_observed", "side": "unclear"}}),
        )
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        agent.state.dialog.side_topic_streak = 2
        assert agent.state.diagnosis.evidence and agent.state.ticket.stage == "phone"

        reopen_identification(agent.state, agent.runtime, "skambinu dėl kito adreso — Dainų 5")

        assert agent.state.diagnosis.evidence == {}
        assert agent.state.ticket.stage is None and agent.state.ticket.context is None
        assert (
            agent.state.diagnosis.evidence_ask_counts == {}
            and agent.state.diagnosis.evidence_conflict is None
        )
        assert agent.state.dialog.side_topic_streak == 0
        assert agent.state.identity.customer_id is None  # identity dropped as before

    def test_scripted_turn_lands_user_message_on_history(self, db_connection):
        # The LLM narrator used to see holes: scripted turns never appended the
        # caller's utterance, so later turns re-asked answered questions.
        from agent.session import AgentSession

        s = AgentSession(caller_phone="+37060012353")
        s.greeting()
        reply = s.handle_turn("neveikia internetas")  # scripted address move, no LLM
        assert "skambinate dėl" in reply  # etalonas #2: no opening anamnesis
        roles = [(m["role"], m.get("content")) for m in s.state.messages]
        assert ("user", "neveikia internetas") in roles
        assert roles[-1][0] == "assistant" and "skambinate dėl" in roles[-1][1]

    def test_llm_turn_appends_user_exactly_once(self, db_connection):
        from unittest.mock import patch as _patch

        from agent.session import AgentSession

        def _stream(**kwargs):
            def _gen():
                yield "Atsakau."
                return _fake_message(content="Atsakau.")

            return _gen()

        s = AgentSession(caller_phone="+37060012353")
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
            s = AgentSession(caller_phone="unknown")
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
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "asked": True,
        }
        agent.state.diagnosis.evidence_ask_counts["lights"] = 1
        agent.state.diagnosis.pending_evidence_key = "lights"

        agent.on_turn_cancelled("Pažiūrėkite, ar dega bent")

        assert agent.state.resolution.procedure["asked"] is True  # early answer will route
        assert (
            agent.state.diagnosis.evidence_ask_counts["lights"] == 0
        )  # wording level not escalated
        assert agent.state.messages[-1]["content"].startswith("Pažiūrėkite")
        assert agent.state.messages[-1]["content"].endswith("—")

    def test_stale_cancel_never_kills_the_next_turn(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.runtime.cancel.set()  # interrupt raced past the turn's end
        reply = identification_scripted_reply(agent.state, agent.runtime, "Labadiena!")
        assert reply  # scripted path unaffected
        assert agent.runtime.cancel.is_set()  # cleared only at a STREAM turn start


class TestSmallTalkBeforeProblem:
    """Live 2026-08-06: "Labadiena!" fell to the LLM, which offered the address
    BEFORE any problem was stated; the ladder then re-offered it (duplicate).
    Small talk pre-problem is scripted now; the facts block guards the rest."""

    def _fresh(self):
        from tests.calls import make_agent

        return make_agent("+37060012353")

    def test_greeting_gets_scripted_ask_problem(self, db_connection):
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply

        agent = self._fresh()
        assert identification_scripted_reply(agent.state, agent.runtime, "Labadiena!") == phrase(
            "identification.ask_problem"
        )
        assert identification_scripted_reply(agent.state, agent.runtime, "Sveiki") == phrase(
            "identification.ask_problem"
        )

    def test_problem_statement_is_not_smalltalk(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._fresh()
        agent.state.intake.problem_type = "internet_down"
        reply = identification_scripted_reply(agent.state, agent.runtime, "neveikia internetas")
        # etalonas #2 (2026-09-03): straight to the address, not ask_problem
        assert reply is not None and "adres" in reply.lower()

    def test_facts_forbid_address_offer_before_problem(self, db_connection):
        from agent.narrator_flow import state_facts_block

        agent = self._fresh()
        facts = state_facts_block(agent.state, agent.runtime) or ""
        assert "PROBLEMA DAR NEPASAKYTA" in facts
        agent.state.intake.problem_type = "internet_down"
        facts2 = state_facts_block(agent.state, agent.runtime) or ""
        assert "PROBLEMA DAR NEPASAKYTA" not in facts2


class TestScriptedWrapUp:
    """After the inform news, ANY non-question turn wraps up deterministically —
    a garbled goodbye ("Nusigaro") had looped 'nesupratau, pakartokite' forever."""

    def _informed(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        agent.state.diagnosis.news_delivered = True
        return agent

    def test_garbled_goodbye_wraps_up(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        # Closing wave block 2 (2026-09-09): a content-bearing turn first gets
        # a REACTION (the caller may have said something real — "Vilma",
        # "sumokėjau"); the cap of 2 still guarantees a garbled goodbye
        # ("Nusigaro") cannot loop the wrap-up — the third turn closes.
        agent = self._informed(db_connection)
        assert identification_scripted_reply(agent.state, agent.runtime, "Nusigaro.") is None
        assert identification_scripted_reply(agent.state, agent.runtime, "Nusigaro.") is None
        reply = identification_scripted_reply(agent.state, agent.runtime, "Nusigaro.")
        assert reply and "Ačiū, kad paskambinote" in reply
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "inform"
        assert agent.state.closing.is_complete is True

    def test_question_after_news_goes_to_llm(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed(db_connection)
        assert (
            identification_scripted_reply(agent.state, agent.runtime, "O kiek turiu sumokėti?")
            is None
        )
        assert agent.state.closing.case_closed is False

    def test_wants_more_goes_to_llm(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed(db_connection)
        assert (
            identification_scripted_reply(
                agent.state, agent.runtime, "Palaukite, dar turiu klausimą"
            )
            is None
        )
        assert agent.state.closing.case_closed is False


class TestThinkerBoundaries:
    """Step 3 — the mąstytojas drives piloted directions but NEVER overrides the
    deterministic mechanics (ladder, clarify contract, wrap-up)."""

    def _agent(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.caller_name = "Jonas"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        return agent

    def test_defers_while_ladder_open(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.identity.result_pending = True  # caller-intro / result still owed
        assert solver_drive_turn(agent.state, agent.runtime, "taip") is None

    def test_defers_while_end_confirm_pending(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.dialog.end_confirm_pending = True
        assert solver_drive_turn(agent.state, agent.runtime, "taip") is None

    def test_defers_until_caller_intro_done(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.identity.caller_name = None  # ladder's last rung not done
        assert solver_drive_turn(agent.state, agent.runtime, "taip") is None

    def test_off_switch_reverts_to_walker(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        monkeypatch.setenv("SOLVER_DRIVE", "off")
        agent = self._agent(db_connection)
        assert solver_drive_turn(agent.state, agent.runtime, "taip") is None

    def test_walker_declared_direction_falls_back(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        # R4b: the PACK declares its driver. A verdict whose pack says walker
        # (or declares nothing and is not in the legacy pilot set) stays with
        # the step tree — the solver hands the turn back.
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        from agent import faults

        monkeypatch.setattr(faults, "driver", lambda v: "walker")
        agent = self._agent(db_connection)
        agent.state.resolution.procedure = {"verdict": "foreign_mac", "step": "confirm_change"}
        assert solver_drive_turn(agent.state, agent.runtime, "taip") is None

    def test_solver_declared_direction_is_driven(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        # All internet packs now declare vairuotojas: solveris (2026-08-13) —
        # the evidence engine asks the first missing fact from the pack.
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        agent = self._agent(db_connection)
        agent.state.resolution.procedure = {"verdict": "foreign_mac", "step": "confirm_change"}
        reply = solver_drive_turn(agent.state, agent.runtime, "taip")
        assert reply is not None and "keitėte routerį" in reply


class TestDriveRepeatBailout:
    """The thinker asked the SAME thing twice despite answers -> deterministic
    bailout to the registration offer (observed live: 6x verbatim loop)."""

    def test_distrust_loop_hands_wheel_to_walker(self, db_connection, monkeypatch):
        from agent.perception_flow import ingest_client_evidence
        from agent.solver_flow import solver_drive_turn

        # Ledger v2: while EVIDENCE is missing, the evidence engine (not the
        # solver) asks — deterministically, bench or no bench. The distrust
        # bailout now matters where the SOLVER actually drives: the bridge
        # phase (evidence confirmed, has_computer=yes -> _evidence_drive None).
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.caller_name = "Andrius"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_power"}
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        ingest_client_evidence(
            agent.state, agent.runtime, "Maitinimo laidas gerai įkištas, bandžiau kitą rozetę"
        )
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį")
        agent.state.diagnosis.facts_recap_state = (
            "done"  # recap checkpoint tested elsewhere (round 3)
        )
        agent.state.resolution.drive_repeats = 2  # repeat/disambiguate streak already observed

        # 2026-08-21 (fix 2): the bridge is WALKED through the pack's guided
        # steps — the solver never drives it, so there is no distrust loop to
        # bench; the evidence layer syncs the walker to the cable step instead.
        assert (
            solver_drive_turn(agent.state, agent.runtime, "gerai gerai") is None
        )  # walker owns the bridge
        assert agent.state.resolution.procedure.get("solution_synced") == "dr_pick_cable"
        assert (
            solver_drive_turn(agent.state, agent.runtime, "nedega") is None
        )  # and keeps owning it

    def test_evidence_keeps_driving_after_solver_bench(self, db_connection, monkeypatch):
        from agent.solver_flow import solver_drive_turn

        # The rewind trap is dead: a benched solver no longer strands the call
        # at a stale step — missing evidence still gets asked deterministically.
        monkeypatch.setenv("SOLVER_DRIVE", "on")
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.caller_name = "Andrius"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        agent.state.resolution.drive_disabled = True  # solver already benched

        reply = solver_drive_turn(agent.state, agent.runtime, "na, nežinau")
        assert reply is not None and "elektra" in reply  # ivykiai first (2026-09-03)


class TestBindDiscipline:
    """2026-08-04 (Andrius): a change runs ONLY when the client did the work and
    agreed — the solver had the engine bind FOUR turns early, and its escalate
    wrote a raw verdict key as the ticket and lost ticket_id from the record."""

    def _driving_agent(self, monkeypatch, simulate="on"):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "SIMULATE_BRIDGE", simulate)
        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.caller_name = "Andrius"
        agent.state.intake.anamnesis_when = "vakar"
        agent.state.intake.anamnesis_trigger = "audra"
        agent.state.diagnosis.hypothesis = {"cause": "no_mac_observed", "status": "testing"}
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        return agent

    def test_fix_deferred_until_plugged(self, db_connection, monkeypatch):
        from agent.solver_flow import drive_propose_fix

        agent = self._driving_agent(monkeypatch)
        # First deferral = the transition + bridge OFFER (2026-08-05); later
        # deferrals wait for the plug-in. Never a premature action either way.
        first = drive_propose_fix(
            agent.state, agent.runtime, "Pririšu dabar!", "gerai, tuoj bandysiu"
        )
        assert "Ar turite kompiuterį" in first
        again = drive_propose_fix(
            agent.state, agent.runtime, "Pririšu dabar!", "gerai, tuoj bandysiu"
        )
        assert "Kai prijungsite" in again
        assert agent.state.resolution.bridge_bound is False

    def test_plugged_report_binds_once(self, db_connection, monkeypatch):
        # Tools are FAKED so the shared session DB is not mutated (a real bind here
        # flipped CUST009 healthy and broke a later ordering-dependent graph test).
        import json as _json

        from agent.solver_flow import drive_propose_fix

        agent = self._driving_agent(monkeypatch)
        calls = []

        def fake_execute(name, args):
            calls.append(name)
            if name == "diagnose_connection":
                # After the (noop) simulation the line "sees" the plugged PC.
                reason = "foreign_mac" if "simulated" in calls else "no_mac_observed"
                return _json.dumps({"success": True, "verdict": {"reason": reason}})
            return _json.dumps({"success": True})

        install_fake_tools(monkeypatch, fake_execute)
        monkeypatch.setattr(
            "agent.executor_flow.simulate_bridge_connection",
            lambda state, rt: calls.append("simulated"),
        )
        monkeypatch.setattr("agent.narrator_flow.augment_tool_result", lambda state, rt, n, o: o)

        reply = drive_propose_fix(agent.state, agent.runtime, "", "Įkišau į kompiuterį")
        assert agent.state.resolution.bridge_bound is True
        assert "update_mac" in calls  # the bind actually ran
        assert "pririš" in reply.lower() or "atsirado" in reply.lower()
        # Never twice.
        again = drive_propose_fix(agent.state, agent.runtime, "", "įkišau dar kartą")
        assert "jau pririštas" in again
        assert calls.count("update_mac") == 1

    def test_drive_escalate_uses_state_ticket(self, db_connection, monkeypatch):
        from agent.solver_flow import drive_escalate

        agent = self._driving_agent(monkeypatch)
        q1 = drive_escalate(agent.state, agent.runtime, None)
        assert "Ar tiks numeris" in q1  # contacts dialogue first (2026-08-04)
        say = _complete_ticket_dialogue(agent)
        assert agent.state.ticket.ticket_id  # recorded on the call, not lost
        assert agent.state.closing.closed_reason == "registered"
        assert "Užregistravau" in say and "leisti" not in say  # a fact, not a request
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "dingo vakar" in details and "audra" in details  # anamnesis rides along


class TestTicketDialogue:
    """2026-08-04: every registration first collects the contact number (ALWAYS
    asked, never assumed from caller-ID/DB) and when to call — then registers with
    the contacts on the ticket."""

    def _agent_at_consent(self, monkeypatch):
        import os

        from tests.calls import make_agent

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.caller_name = "Andrius"
        agent.state.identity.caller_relation = "holder"
        agent.state.intake.anamnesis_when = "vakar"
        agent.state.diagnosis.hypothesis = {
            "cause": "no_mac_observed",
            "status": "testing",
            "because": ["linijoje nematomas įrenginys"],
        }
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "escalate",
            "asked": True,
        }
        return agent

    def test_consent_starts_dialogue_not_immediate_ticket(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.walker_flow import walk_resolution

        agent = self._agent_at_consent(monkeypatch)
        walk_resolution(agent.state, agent.runtime, "gerai, tinka")
        assert agent.state.ticket.ticket_id is None  # not yet — contacts first
        assert agent.state.ticket.stage == "phone"
        assert "Ar tiks numeris" in identification_scripted_reply(
            agent.state, agent.runtime, "gerai, tinka"
        )

    def test_full_dialogue_lands_contacts_on_ticket(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)  # asks the phone question
        # Q1 answer: "tiks šis" -> the number they call from.
        pre_turn_guards(agent.state, agent.runtime, "Taip, tiks šis numeris")
        assert agent.state.ticket.contact_phone == "+37060012353"
        assert agent.state.ticket.stage == "hours"
        identification_scripted_reply(
            agent.state, agent.runtime, "Taip, tiks šis numeris"
        )  # asks hours
        # Q2 answer -> hours; the scripted turn then registers + closes.
        pre_turn_guards(agent.state, agent.runtime, "Po penkių vakare")
        assert agent.state.ticket.stage == "done"
        reply = identification_scripted_reply(agent.state, agent.runtime, "Po penkių vakare")
        assert "Užregistravau" in reply
        assert agent.state.ticket.ticket_id and agent.state.closing.case_closed
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "Andrius (holder), tel. +37060012353" in details
        assert "skambinti: Po penkių vakare" in details

    def test_dictated_number_captured(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "Geriau skambinkit 8 612 34 567")
        assert agent.state.ticket.contact_phone == "861234567"

    def test_farewell_mid_dialogue_registers_with_defaults(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "viso gero")  # done talking — defaults kick in
        assert agent.state.ticket.stage == "done"
        reply = identification_scripted_reply(agent.state, agent.runtime, "viso gero")
        assert "Užregistravau" in reply
        assert agent.state.ticket.contact_phone == "+37060012353"
        assert agent.state.ticket.contact_hours == "bet kada"
        assert agent.state.ticket.ticket_id

    def test_intro_announces_cause_once(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.ticket_flow import begin_ticket_dialogue, ticket_stage_reply

        # The FIRST stage reply carries "Registruoju gedimą — {priežastis}"; a
        # re-ask does not repeat the intro.
        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        first = identification_scripted_reply(agent.state, agent.runtime, None)
        assert "Registruoju meistrą" in first and "maršrutizatorius" in first
        assert "Ar tiks numeris" in first
        again = ticket_stage_reply(agent.state, agent.runtime)
        assert "Registruoju gedimą" not in again  # intro said once

    def test_question_mid_dialogue_goes_to_llm_and_stage_holds(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        # "Bet kada galima skambinti?" is the caller ASKING — live it was captured
        # verbatim as the HOURS answer and landed on the ticket. It must divert to
        # the LLM (scripted None) and the stage must not advance.
        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "taip, tiks šis")
        assert agent.state.ticket.stage == "hours"
        identification_scripted_reply(agent.state, agent.runtime, "taip, tiks šis")
        pre_turn_guards(
            agent.state, agent.runtime, "Tu sakė, užregistravai jau. Bet kada galima skambinti?"
        )
        assert agent.state.ticket.stage == "hours"  # held, not captured
        assert agent.state.ticket.contact_hours is None
        assert (
            identification_scripted_reply(agent.state, agent.runtime, "Bet kada galima skambinti?")
            is None
        )
        facts = state_facts_block(agent.state, agent.runtime)
        assert facts and "TIKETO DIALOGAS" in facts and "kada patogiausia" in facts
        # A plain answer next turn still lands.
        agent.state.turn.ticket_offscript_question = False
        pre_turn_guards(agent.state, agent.runtime, "bet kada")
        assert agent.state.ticket.contact_hours == "bet kada"

    def test_done_announce_repeats_number_and_hours(self, db_connection, monkeypatch):
        from agent.ticket_flow import begin_ticket_dialogue

        # "Kokiu numeriu?" was asked twice live and got a goodbye — the announce
        # now repeats the number + hours so the question never arises.
        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        reply = _complete_ticket_dialogue(agent)
        assert "+370 600 12353" in reply
        assert "bet kada" in reply

    def test_garbled_yes_and_stt_punctuation_stay_off_the_ticket(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        # Live: STT "T." (of "Taip") became tel. "T." and "Bet kada?" kept the "?"
        # on the ticket and in the announce.
        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "T.")
        assert agent.state.ticket.contact_phone == "+37060012353"  # backchannel yes -> caller-ID
        identification_scripted_reply(agent.state, agent.runtime, "T.")
        pre_turn_guards(agent.state, agent.runtime, "Bet kada?")
        assert agent.state.ticket.contact_hours == "Bet kada"
        reply = identification_scripted_reply(agent.state, agent.runtime, "Bet kada?")
        assert "bet kada" in reply

    def test_trigger_utterance_not_swallowed_as_phone(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        # Live 2026-08-05: escalate fired mid-turn and the SAME utterance
        # ("Neturi kompiutera") was captured as the phone number, question
        # never asked. Answers count only after the question was asked.
        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "Neturi kompiutera")  # same-turn trigger phrase
        assert agent.state.ticket.contact_phone is None
        assert agent.state.ticket.stage == "phone"  # still waiting for its question
        first = identification_scripted_reply(agent.state, agent.runtime, "Neturi kompiutera")
        assert "Ar tiks numeris" in first  # the question goes out now

    def test_garbage_phone_answer_reasks_then_defaults(self, db_connection, monkeypatch):
        # Live: "Neturi kompiutera" landed as tel. on the ticket. Now: one
        # scripted retry; a second unclear answer defaults to caller-ID.
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)  # phone asked
        pre_turn_guards(agent.state, agent.runtime, "Kurs komentai")  # STT garbage
        assert agent.state.ticket.contact_phone is None
        reply = identification_scripted_reply(agent.state, agent.runtime, "Kurs komentai")
        assert reply == phrase("identification.ticket_phone_retry")
        pre_turn_guards(
            agent.state, agent.runtime, "Visai nesuprantu ko klausiat"
        )  # second garbage
        assert agent.state.ticket.contact_phone == "+37060012353"  # caller-ID default
        assert agent.state.ticket.stage == "hours"

    def test_garbage_hours_answer_reasks_then_defaults(self, db_connection, monkeypatch):
        # Live: "Kurs komentai" became "skambinti galima kurs komentai".
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        identification_scripted_reply(agent.state, agent.runtime, None)
        pre_turn_guards(agent.state, agent.runtime, "taip, tiks šis")
        identification_scripted_reply(agent.state, agent.runtime, "taip, tiks šis")  # hours asked
        pre_turn_guards(agent.state, agent.runtime, "Kurs komentai")
        assert agent.state.ticket.contact_hours is None
        reply = identification_scripted_reply(agent.state, agent.runtime, "Kurs komentai")
        assert reply == phrase("identification.ticket_hours_retry")
        pre_turn_guards(agent.state, agent.runtime, "Nu nezinau visai")  # second garbage -> default
        assert agent.state.ticket.contact_hours == "bet kada"
        assert agent.state.ticket.stage == "done"

    def test_first_fix_deferral_is_transition_and_offer(self, db_connection, monkeypatch):
        from agent.solver_flow import drive_propose_fix

        # Live: solver jumped to bind-speak ("pririšiu įrenginį") with no
        # transition — caller asked "Apie kokį kompiuterį kalbat?". The FIRST
        # deferral now announces the dead router and OFFERS the bridge.
        agent = self._agent_at_consent(monkeypatch)
        install_fake_tools(
            monkeypatch, lambda name, args: json.dumps({"verdict": {"reason": "no_mac_observed"}})
        )
        first = drive_propose_fix(agent.state, agent.runtime, "", "nedega lemputės")
        assert "routeris sugedęs" in first and "Ar turite kompiuterį" in first
        second = drive_propose_fix(agent.state, agent.runtime, "", "dar nieko nedariau")
        assert "pasakykite" in second  # the short wait line afterwards

    def test_plugged_into_computer_runs_bind_path_not_solver(self, db_connection, monkeypatch):
        # Eval S4: "Įkišau į kompiuterį" got yet another solver disambiguate and
        # the bind never ran. The plug-in report is ENGINE territory now — it
        # routes to _drive_propose_fix (whose own discipline still requires the
        # device to actually be visible before any bind).
        import os

        from agent.solver_flow import solver_drive_turn

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution.procedure["step"] = "dr_offer_bridge"
        called = {}

        def fake_propose(say, user_input):
            called["ran"] = True
            return "Pririšu įrenginį."

        monkeypatch.setattr(
            "agent.solver_flow.drive_propose_fix",
            lambda state, rt, say, text: fake_propose(say, text),
        )
        reply = solver_drive_turn(agent.state, agent.runtime, "Įkišau į kompiuterį")
        assert called.get("ran") is True
        assert reply == "Pririšu įrenginį."

    def test_tik_kompiuteri_is_not_a_no_device_answer(self, db_connection, monkeypatch):
        # "Neturiu kito routerio, tik kompiuterį" after the bridge offer must
        # NOT escalate — the caller HAS a computer (eval S4 regression).
        import os

        from agent.solver_flow import solver_drive_turn

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar turite kompiuterį, kad paleistume internetą?"}
        )
        agent.state.resolution.drive_disabled = True  # isolate: no solver LLM call
        reply = solver_drive_turn(
            agent.state, agent.runtime, "Neturiu kito routerio, tik kompiuterį"
        )
        assert agent.state.ticket.stage is None  # no escalation fired
        # (evidence drive may still ask its next question — that is fine)

    def test_no_device_after_bridge_offer_escalates_deterministically(
        self, db_connection, monkeypatch
    ):
        # Live 2026-08-05: "Neturiu." after "Ar turite kompiuterį?" sent the
        # solver into a 6x disambiguate streak and a walker rewind. The answer
        # is ENGINE territory now: escalate the same turn, no solver involved.
        import os

        from agent.solver_flow import solver_drive_turn

        monkeypatch.setitem(os.environ, "SOLVER_DRIVE", "on")
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution.procedure["step"] = "dr_offer_bridge"
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "Panašu, kad routeris sugedęs. Ar turite kompiuterį, kad galėtume "
                    "laikinai paleisti internetą per jį?"
                ),
            }
        )
        reply = solver_drive_turn(
            agent.state, agent.runtime, "Neturiu, internetą naudoju tik telefonu."
        )
        assert reply is not None and "Ar tiks numeris" in reply
        assert agent.state.ticket.stage == "phone"

    def test_registration_claim_without_ticket_starts_dialogue(self, db_connection, monkeypatch):
        from agent.ticket_flow import registration_claim_guard

        # Live 2026-08-05: narrator said "Užregistravau gedimą…", ticket_id None,
        # caller hung up trusting it. The claim now pulls the real dialogue in.
        agent = self._agent_at_consent(monkeypatch)
        extra = registration_claim_guard(
            agent.state,
            agent.runtime,
            "Supratau. Užregistravau gedimą, kolegos susisieks su jumis.",
        )
        assert extra and "Ar tiks numeris" in extra
        assert agent.state.ticket.stage == "phone"
        # Honest replies pass untouched.
        agent2 = self._agent_at_consent(monkeypatch)
        assert (
            registration_claim_guard(agent2.state, agent2.runtime, "Patikrinkime lemputes.") is None
        )

    def test_hangup_mid_strategy_registers_safety_ticket(self, db_connection, monkeypatch):
        # Live 2026-08-05: the call ended via the UI button mid-strategy — no
        # ticket, despite a promised registration. end_session now registers
        # from state with the interruption on the record.
        agent = self._agent_at_consent(monkeypatch)
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket.ticket_id
        assert agent.state.closing.closed_reason == "registered"
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "Pokalbis nutrūko" in details
        assert "+37060012353" in details  # caller-ID default contact

    def test_hangup_after_resolved_call_registers_nothing(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent.state.closing.case_closed = True
        agent.state.closing.closed_reason = "resolved"
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket.ticket_id is None

    def test_hangup_net_skips_when_line_is_healthy(self, db_connection, monkeypatch):
        # Live 2026-08-06 (TKT00D19E54): the caller confirmed "veikia!" and hung
        # up before the goodbye — the net registered a technician for a HEALTHY
        # line. The line's current truth now decides: fresh diagnose healthy ->
        # no ticket, closed as resolved.
        agent = self._agent_at_consent(monkeypatch)
        install_fake_tools(
            monkeypatch, lambda name, args: json.dumps({"verdict": {"reason": "healthy_to_router"}})
        )
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.closed_reason == "resolved"

    def test_hangup_net_skips_on_recorded_fix(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        agent.state.resolution.procedure["telemetry_fixed"] = True
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.closed_reason == "resolved"

    def test_hangup_net_still_registers_when_fault_persists(self, db_connection, monkeypatch):
        agent = self._agent_at_consent(monkeypatch)
        # _agent_at_consent uses CUST009 whose seeded line still shows no_mac —
        # the real diagnose read confirms the fault persists -> ticket.
        agent.end_session(outcome="client_closed")
        assert agent.state.ticket.ticket_id
        assert agent.state.closing.closed_reason == "registered"

    def test_explicit_refusal_cancels_without_ticket(self, db_connection, monkeypatch):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.ticket_flow import begin_ticket_dialogue, ticket_stage_reply

        agent = self._agent_at_consent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        # Cancelling is a one-way door (2026-08-11): the first refusal gets ONE
        # confirm question; only the confirmed refusal cancels and closes.
        pre_turn_guards(agent.state, agent.runtime, "ne, nereikia registruoti nieko")
        assert agent.state.ticket.stage == "phone"
        assert "tikrai nereikia" in ticket_stage_reply(agent.state, agent.runtime)
        pre_turn_guards(agent.state, agent.runtime, "nereikia")
        assert agent.state.ticket.stage == "cancelled"
        reply = identification_scripted_reply(agent.state, agent.runtime, "nereikia")
        assert "neregistruoju" in reply
        assert agent.state.ticket.ticket_id is None
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "declined"

    def test_escalate_arrival_starts_dialogue_even_with_consent_step(
        self, db_connection, monkeypatch
    ):
        from agent.walker_flow import ensure_action_done

        # Live 2026-08-04: arrival at a consent ESCALATE was narrated by the LLM
        # ("užregistravau…" before anything happened). Arrival now begins the
        # dialogue deterministically the same turn, consent step or not.
        agent = self._agent_at_consent(monkeypatch)
        assert ensure_action_done(agent.state, agent.runtime) is True
        assert agent.state.ticket.stage == "phone"


class TestPromptPrefixHygiene:
    """Prompt hygiene step 1 (2026-08-26): the node prompt joins the LEADING
    system message (one byte-stable, cacheable prefix per node); the dynamic
    facts block stays a trailing system message; directive turns keep the
    lean persona prompt with NO node prompt."""

    def test_node_prompt_folds_into_the_leading_system(self, db_connection):
        from agent.narrator_flow import build_messages

        from tests.calls import make_agent

        agent = make_agent("unknown")
        messages = build_messages(
            agent.state, agent.runtime, user_input="Labas", node_prompt="NODE-RULES-MARKER"
        )
        assert messages[0]["role"] == "system"
        assert "NODE-RULES-MARKER" in messages[0]["content"]
        # no trailing system message carries the node prompt any more
        assert all("NODE-RULES-MARKER" not in m.get("content", "") for m in messages[1:])
        # and the prefix is byte-stable across turns
        again = build_messages(
            agent.state, agent.runtime, user_input="Kitas", node_prompt="NODE-RULES-MARKER"
        )
        assert again[0]["content"] == messages[0]["content"]

    def test_directive_turn_keeps_lean_prompt_without_node_rules(self, db_connection):
        from agent.narrator_flow import build_messages

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.ident = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        messages = build_messages(
            agent.state, agent.runtime, user_input="Labas", node_prompt="NODE-RULES-MARKER"
        )
        assert all("NODE-RULES-MARKER" not in m.get("content", "") for m in messages)
