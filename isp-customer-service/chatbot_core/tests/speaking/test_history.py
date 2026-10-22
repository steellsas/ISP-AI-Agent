"""
Hygiene step 3 — istorija v2 (Andrius 2026-08-27): a deterministic summary
from STATE bridges the trimmed window; a recall trigger pulls the caller's
own earlier lines back in; nothing is ever deleted from state.messages.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext

from tests.tool_fakes import install_fake_tools

FUNCTION = "Istorija"


def _agent(db_connection=None):
    from tests.calls import make_agent

    agent = make_agent("+37060012353")
    agent.state.intake.problem_type = "internet_down"
    agent.state.intake.anamnesis_when = "yesterday"
    agent.state.identity.customer_id = "CUST009"
    agent.state.identity.customer_address = "Šiauliai, Vilniaus g. 29"
    return agent


class TestHistorySummary:
    def test_no_summary_while_history_fits(self, db_connection):
        from agent.speak.history import history_summary

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "labas"}] * 5
        assert history_summary(agent.state, agent.runtime) is None

    def test_summary_bridges_the_cut(self, db_connection):
        from agent.speak.history import history_summary

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": f"r{i}"} for i in range(30)]
        text = history_summary(agent.state, agent.runtime)
        assert text and "SANTRAUKA" in text
        assert "internet_down" in text and "vakar" in text
        assert "Vilniaus g. 29" in text

    def test_summary_lands_before_the_window(self, db_connection):
        from agent.speak.node import build_messages

        agent = _agent()
        agent.state.messages = [
            {"role": "user" if i % 2 else "assistant", "content": f"replika {i}"} for i in range(30)
        ]
        messages = build_messages(agent.state, agent.runtime, "intake")
        idx = [
            i
            for i, m in enumerate(messages)
            if m["role"] == "system" and "SANTRAUKA" in m.get("content", "")
        ]
        assert len(idx) == 1
        # the summary comes right after the prefix, before the windowed history
        assert idx[0] == 1
        # nothing was deleted from state — prompt assembly never mutates it
        assert len(agent.state.messages) == 30


class TestRecallTrigger:
    def test_saskiau_pulls_the_old_line_back(self, db_connection):
        from agent.speak.history import recall_lines

        agent = _agent()
        old = [{"role": "user", "content": "internetas dingo po didelės audros vakar"}]
        filler = [
            {"role": "user" if i % 2 else "assistant", "content": f"replika {i}"} for i in range(25)
        ]
        agent.state.messages = old + filler
        agent.state.dialog.last_heard = "juk sakiau — po audros dingo"
        note = recall_lines(agent.state, agent.runtime)
        assert note and "audros" in note and "PRIMENA" in note

    def test_no_marks_no_recall(self, db_connection):
        from agent.speak.history import recall_lines

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "po audros"}] * 30
        agent.state.dialog.last_heard = "nedega lemputė"
        assert recall_lines(agent.state, agent.runtime) is None

    def test_recent_reference_needs_no_recall(self, db_connection):
        from agent.speak.history import recall_lines

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "po audros dingo"}] * 5
        agent.state.dialog.last_heard = "sakiau — po audros"
        assert (
            recall_lines(agent.state, agent.runtime) is None
        )  # the line is still inside the window


def _fake_message(content=None, tool_calls=None):
    """Build a stand-in for the litellm assistant message object."""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


# --- from test_agent.py ---


class TestReviewGaps:
    """2026-08-07 architecture review fixes."""

    def test_reopen_clears_evidence_and_dialogue_state(self, db_connection, monkeypatch):
        # Stale-state bomb: after an address correction the OLD account's
        # telemetry facts (the verdict!) survived in the ledger.
        import os

        from agent.decide.rules.identification import reopen_identification
        from agent.execute.observe import update_state_from_observation
        from agent.execute.ticket import request_ticket
        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "diagnose_connection",
            json.dumps({"verdict": {"reason": "no_mac_observed", "side": "unclear"}}),
        )
        request_ticket(agent.state, agent.runtime, "sprendimas_baigtas")
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
