import pytest
from agent.call_record.finalizer import build_call_summary, finalize

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


class TestSpeakPrompt:
    """The speaker's prompt: persona and the caller's number, and NO tools (M5)."""

    def test_prompt_has_no_tools_and_carries_the_phone(self):
        from agent.speak.node import speak_prompt

        prompt = speak_prompt("intake", "+37060012345", "lt")

        assert "+37060012345" in prompt
        assert "You have NO tools" in prompt
        assert "find_customer" not in prompt


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
    """What the speaker is sent: the owner prefix, the history, the card."""

    def test_build_messages_leads_with_the_skill_prefix(self):
        """Wave 2b: the prefix is the core prompt + the ONE skill this reply needs."""
        from agent.speak.node import build_messages, speak_prompt
        from agent.speak.skill import skill_for

        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        messages = build_messages(agent.state, agent.runtime, "intake")

        skill = skill_for(agent.state, "intake")
        assert skill == "ask_identity"
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == speak_prompt(skill, "+37060012345", "lt")

    def test_build_messages_carries_the_history(self):
        from agent.speak.node import build_messages

        from tests.calls import make_agent

        agent = make_agent("+37060012345")
        agent.state.messages.append({"role": "user", "content": "Labas"})

        messages = build_messages(agent.state, agent.runtime, "intake")

        assert any(m["role"] == "user" and "Labas" in m["content"] for m in messages)


class TestPromptLoader:
    """Tests for prompt loading."""

    def test_load_speak_prompt(self):
        """The speaker's core prompt composes and localises."""
        from agent.prompts import load_speak_prompt

        prompt = load_speak_prompt(caller_phone="+37060012345", language="lt")

        assert isinstance(prompt, str)
        assert "+37060012345" in prompt
        assert "Lithuanian" in prompt
        assert "You have NO tools" in prompt


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
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "Ačiū, viso gero, sudie")
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "outage"
        assert agent.state.closing.is_complete is True

    def test_no_farewell_keeps_call_open(self, db_connection):
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        maybe_close_inform(agent.state, agent.runtime, "O kada tiksliai sutvarkysite?")
        assert agent.state.closing.case_closed is False

    def test_active_strategy_never_closed_here(self, db_connection):
        """A live troubleshooting strategy belongs to the walker — a mid-flow 'ne'
        must not end the call."""
        from agent.decide.rules.closing import maybe_close_inform

        agent = self._informed_agent()
        agent.state.diagnosis.outage_reported = False
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "foreign_mac"}
        agent.state.resolution.procedure = {"verdict": "foreign_mac", "step": "confirm_change"}
        maybe_close_inform(agent.state, agent.runtime, "ne")
        assert agent.state.closing.case_closed is False


def _complete_ticket_dialogue(agent):
    """Walk the 2-question contact dialogue (2026-08-04) to the registration.
    Each stage question must be ASKED before its answer counts (2026-08-05)."""
    from agent.decide.rules.head import turn_head
    from agent.decide.rules.reply import scripted_words

    scripted_words(agent.state, agent.runtime, None)  # intro + phone question
    turn_head(agent.state, agent.runtime, "taip, tiks šis")
    scripted_words(agent.state, agent.runtime, "taip, tiks šis")  # hours question
    turn_head(agent.state, agent.runtime, "bet kada")
    return scripted_words(agent.state, agent.runtime, "bet kada")


class TestAutoRegisterEscalate:
    """consent=False ESCALATE (dr_register_router): the registration is a necessity —
    the engine registers ON ARRIVAL and closes; no consent question, no misread."""

    def test_arrival_registers_and_closes(self, db_connection, monkeypatch):
        import os

        from agent.execute.diagnosis import ensure_action_done

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
        from agent.perceive.detectors import detect_ticket_consent

        assert detect_ticket_consent("Lauksiu skambučio, ačiū") == "yes"

    def test_farewell_stt_garbles_close(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Neturiu, neturiu, visą gerą") is True
        assert detect_farewell("visa gera, ačiū") is True


@pytest.mark.usefixtures("walker_driven")
class TestAddressGuards:
    """Round-3 live bugs: a garbled reply must not commit the offered address, and a
    post-identification correction must reopen identification."""

    def test_garbled_taip_nebija_is_not_a_confirm(self):
        from agent.perceive.detectors import detect_address_confirm

        assert detect_address_confirm("Taip, nebija") is None  # mixed -> re-ask
        assert detect_address_confirm("Taip, tvirtinu") == "yes"
        assert detect_address_confirm("Ne, dėl kito adreso") == "no"
        # Problem words are not denials: "neveikia" alongside taip still confirms.
        assert detect_address_confirm("Taip, neveikia internetas dėl to adreso") == "yes"

    def test_pre_turn_guard_vetoes_commit(self, db_connection):
        from agent.decide.rules.head import turn_head
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 3?"}
        )
        turn_head(agent.state, agent.runtime, "Taip, nebija")
        assert agent.state.turn.address_confirm_note is not None  # veto: do not resolve the offer
        facts = context_card(agent.state, agent.runtime)
        assert facts and "NEPATVIRTINTAS" in facts

    def test_correction_asks_confirmation_then_reopens(self, db_connection):
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        # Etalonas №3 (2026-09-03): a correction no longer reopens INSTANTLY —
        # one confirmation question first; a "taip" (or a named new address)
        # then drops the identity.
        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.identity.customer_address = "Šiauliai, Tilžės g. 60-3"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        turn_head(agent.state, agent.runtime, "Tai ne dėl to adresų skambinu")
        assert agent.state.identity.customer_id == "CUST101"  # NOT dropped yet
        assert agent.state.identity.reopen_confirm_utterance
        reply = scripted_words(agent.state, agent.runtime, "Tai ne dėl to adresų skambinu")
        assert reply and "tikrai" in reply  # the confirmation question
        # A-2 (2026-09-07): the ANSWER is read in pre_turn_guards (the turn head,
        # before the solver/walker can consume it) — mirror the live sequence.
        turn_head(agent.state, agent.runtime, "Taip, dėl kito adreso")
        assert agent.state.identity.customer_id is None  # identity dropped after the yes
        assert agent.state.diagnosis.verdicts == {}  # per-account conclusions dropped
        assert agent.state.turn.reopen_note is True


class TestAddressSpeech:
    def test_spoken_address_form(self):
        from agent.voice_pipeline import speech_text as n

        assert n("Ar skambinate dėl Tilžės g. 60-7?") == (
            "Ar skambinate dėl Tilžės gatvė, namas 60, butas 7?"
        )
        assert n("Radau: Žeimių g. 12, butas 6") == "Radau: Žeimių gatvė 12, butas 6"
        assert n("Jokio adreso čia nėra") == "Jokio adreso čia nėra"


class TestFarewellPurity:
    def test_garbled_content_with_ne_is_not_a_farewell(self, db_connection):
        # Live 2026-08-10: "Ne daganiai 1." (=nedega nė viena) fast-forwarded
        # the ticket dialogue to done-with-defaults. The bare-"ne" fallback now
        # requires EVERY token to be a known closing word.
        from agent.perceive.detectors import detect_farewell

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

        from agent.decide.rules.identification import reopen_identification
        from agent.execute.observe import update_state_from_observation
        from agent.execute.ticket import begin_ticket_dialogue
        from agent.perceive.evidence import ingest_client_evidence

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
            and agent.state.diagnosis.contradiction is None
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
            _patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            _patch("agent.speak.node.get_last_call_stats", return_value={}),
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
            patch("agent.speak.node.stream_tool_completion", side_effect=slow_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
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

        from agent.speak.node import on_turn_cancelled

        on_turn_cancelled(agent.state, agent.runtime, "Pažiūrėkite, ar dega bent")

        assert agent.state.resolution.procedure["asked"] is True  # early answer will route
        assert (
            agent.state.diagnosis.evidence_ask_counts["lights"] == 0
        )  # wording level not escalated
        assert agent.state.messages[-1]["content"].startswith("Pažiūrėkite")
        assert agent.state.messages[-1]["content"].endswith("—")

    def test_stale_cancel_never_kills_the_next_turn(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.runtime.cancel.set()  # interrupt raced past the turn's end
        reply = scripted_words(agent.state, agent.runtime, "Labadiena!")
        assert reply  # scripted path unaffected
        assert agent.runtime.cancel.is_set()  # cleared only at a STREAM turn start


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
        from agent.decide.rules.reply import scripted_words

        # Closing wave block 2 (2026-09-09): a content-bearing turn first gets
        # a REACTION (the caller may have said something real — "Vilma",
        # "sumokėjau"); the cap of 2 still guarantees a garbled goodbye
        # ("Nusigaro") cannot loop the wrap-up — the third turn closes.
        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "Nusigaro.") is None
        assert scripted_words(agent.state, agent.runtime, "Nusigaro.") is None
        reply = scripted_words(agent.state, agent.runtime, "Nusigaro.")
        assert reply and "Ačiū, kad paskambinote" in reply
        assert agent.state.closing.case_closed is True
        assert agent.state.closing.closed_reason == "inform"
        assert agent.state.closing.is_complete is True

    def test_question_after_news_goes_to_llm(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "O kiek turiu sumokėti?") is None
        assert agent.state.closing.case_closed is False

    def test_wants_more_goes_to_llm(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._informed(db_connection)
        assert scripted_words(agent.state, agent.runtime, "Palaukite, dar turiu klausimą") is None
        assert agent.state.closing.case_closed is False


class TestPromptPrefixHygiene:
    """The speaker's prefix (core prompt + the turn's skill) is byte-stable per skill, so
    the provider keeps it cached; the card, which changes every turn, trails it."""

    def test_the_skill_folds_into_the_leading_system(self, db_connection):
        from agent.speak.node import build_messages

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.ticket.stage = "phone"
        agent.state.messages.append({"role": "user", "content": "Labas"})
        messages = build_messages(agent.state, agent.runtime, "ticket")
        assert messages[0]["role"] == "system"
        assert "ANSWER DURING THE REGISTRATION" in messages[0]["content"]

        agent.state.messages.append({"role": "user", "content": "Kitas"})
        again = build_messages(agent.state, agent.runtime, "ticket")
        assert again[0]["content"] == messages[0]["content"]

    def test_an_unknown_skill_speaks_with_the_core_prompt(self, db_connection):
        from agent.prompts import load_speak_prompt
        from agent.speak.node import speak_prompt

        assert speak_prompt("no_such_skill", "unknown", "lt") == load_speak_prompt(
            caller_phone="unknown", language="lt"
        )
