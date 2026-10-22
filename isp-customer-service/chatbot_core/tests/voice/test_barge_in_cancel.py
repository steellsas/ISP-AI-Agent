"""Balsas — Generavimo stabdymas."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext

from tests.tool_fakes import install_fake_tools

FUNCTION = "Generavimo stabdymas"


def _fake_message(content=None, tool_calls=None):
    """Build a stand-in for the litellm assistant message object."""
    return SimpleNamespace(content=content, tool_calls=tool_calls)


# --- from test_agent.py ---


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
                        # Whole sentences: the reply guard lets a reply out a sentence at a
                        # time (wave 10), so a word without an end is held, not yielded.
                        yield f"Sakinys {i}. "
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
        agent.state.diagnosis.evidence_ask_counts["lights"] = 1
        agent.state.diagnosis.pending_evidence_key = "lights"

        from agent.speak.node import on_turn_cancelled

        on_turn_cancelled(agent.state, agent.runtime, "Pažiūrėkite, ar dega bent")

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
