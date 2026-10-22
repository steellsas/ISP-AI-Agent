"""Prompt composition: every prompt composes for the active locale, and a broken
include or examples entry fails loudly."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent import prompts
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext
from agent.prompts import PromptError, check_prompts, load_node_prompt

from tests.tool_fakes import install_fake_tools

FUNCTION = "Promptai"


def test_every_prompt_composes():
    check_prompts()


def test_composed_prompts_have_no_open_tokens():
    for path in prompts.PROMPTS_DIR.rglob("*.md"):
        text = load_node_prompt(path.relative_to(prompts.PROMPTS_DIR).with_suffix("").as_posix())
        assert "<<include" not in text and "<<examples" not in text and "<<language>>" not in text


def test_missing_include_fails(tmp_path, monkeypatch):
    (tmp_path / "broken.md").write_text("<<include: partials/nope>>\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    with pytest.raises(PromptError, match="partials/nope"):
        load_node_prompt("broken")


def test_missing_examples_entry_fails(tmp_path, monkeypatch):
    (tmp_path / "broken.md").write_text("Say <<examples:prompt_nope/q1>>.\n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", tmp_path)
    with pytest.raises(PromptError, match="prompt_nope"):
        load_node_prompt("broken")


# --- from test_agent.py ---


class TestSpeakPrompt:
    """The speaker's prompt: persona and the caller's number, and NO tools (M5)."""

    def test_prompt_has_no_tools(self):
        from agent.speak.node import speak_prompt

        prompt = speak_prompt("intake", "+37060012345", "lt")

        assert "You have NO tools" in prompt
        assert "find_customer" not in prompt

    def test_the_phone_travels_only_in_the_ticket_phase(self):
        """v3 6a: the caller's number is needed to register, not to ask about the lights."""
        from agent.speak.node import speak_prompt

        assert "+37060012345" in speak_prompt("ticket_offscript", "+37060012345", "lt", "ticket")
        assert "+37060012345" not in speak_prompt("ask_fact", "+37060012345", "lt", "investigate")

    def test_each_phase_carries_only_its_own_rules(self):
        """v3 6a (docs/review/PROMPTAI.md): identification rules stay out of the fault fix."""
        from agent.speak.node import speak_prompt

        identify = speak_prompt("ask_identity", "+370", "lt", "identify")
        investigate = speak_prompt("ask_fact", "+370", "lt", "investigate")
        assert "contract holder's name" in identify and "contract holder's name" not in investigate
        assert "what you SEE on the line" in investigate and "what you SEE" not in identify


class TestAgentBuildMessages:
    """What the speaker is sent: the owner prefix, the history, the card."""

    def test_build_messages_leads_with_the_skill_prefix(self):
        """Wave 2b: the prefix is the core prompt + the ONE skill this reply needs."""
        from agent.speak.node import build_messages, speak_prompt
        from agent.speak.skill import skill_for

        from tests.calls import make_agent

        agent = make_agent("+37060012345")

        messages = build_messages(agent.state, agent.runtime, "intake")

        from agent.phase import phase_of

        skill = skill_for(agent.state, "intake")
        assert skill == "ask_identity"
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == speak_prompt(
            skill, "+37060012345", "lt", phase_of(agent.state)
        )

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
        assert "+37060012345" not in prompt  # v3 6a: only the ticket phase carries it
        assert "Lithuanian" in prompt
        assert "You have NO tools" in prompt


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
