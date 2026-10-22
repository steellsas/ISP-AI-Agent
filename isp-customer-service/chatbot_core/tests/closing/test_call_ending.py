"""How a call ends (Andrius 2026-10-20): the goodbye is always said; after „Ar dar kuo galiu
padėti?" the agent waits for the answer, and silence ends the call politely."""

from __future__ import annotations

import asyncio

import pytest
from agent.contract.locale import phrase

FUNCTION = "Pabaiga balse"


def test_the_turn_that_ends_the_call_always_says_goodbye(make_state, make_runtime):
    """Live: „viso gero" cut the closing question, the narrator re-asked it and the line
    went down without a goodbye."""
    from agent.decide.rules.reply import plan_reply

    state = make_state("+37060020101")
    state.identity.customer_id = "CUST101"
    state.closing.case_closed = True
    state.closing.is_complete = True
    state.voice.unheard_question = "Ar dar kuo galiu padėti?"

    plan = plan_reply(state, make_runtime(), "Na čia viso gero")

    assert plan.rule == "closing.closed_this_turn"
    assert plan.say.kind == "phrase" and plan.say.text == phrase("identification.goodbye")
    assert state.voice.unheard_question is None


def test_a_closed_case_with_the_call_still_open_is_answered_by_the_narrator(
    make_state, make_runtime
):
    from agent.decide.rules.reply import plan_reply

    state = make_state("+37060020101")
    state.identity.customer_id = "CUST101"
    state.closing.case_closed = True  # not complete: the caller may still ask

    plan = plan_reply(state, make_runtime(), "O kada bus sutvarkyta?")
    assert plan.say.kind == "directive"


@pytest.fixture
def session():
    from agent import AgentSession

    return AgentSession(caller_phone="+37060020101")


def test_the_closing_question_is_recognised(session):
    session._state.dialog.last_question = "Ačiū! Patikrinau. Ar dar kuo galiu padėti?"
    assert session.awaiting_closing_answer()
    session._state.dialog.last_question = "O su kuo kalbu — koks jūsų vardas?"
    assert not session.awaiting_closing_answer()


def test_silence_after_the_closing_question_ends_the_call(session):
    session._state.dialog.last_question = "Ar dar kuo galiu padėti?"
    text = session.close_on_silence()
    assert text == phrase("identification.silence_goodbye")
    assert session.is_complete
    assert not session.awaiting_closing_answer()


pytest.importorskip("pipecat")


def test_the_pipecat_call_says_goodbye_and_hangs_up_on_closing_silence(monkeypatch):
    from app.pipecat_call import EngineProcessor, SpokenTracker, StandaloneTurns
    from pipecat.frames.frames import EndWorkerFrame, LLMTextFrame

    monkeypatch.setenv("CLOSING_SILENCE_S", "0")
    monkeypatch.setenv("GOODBYE_HANGUP_S", "0")

    class Session:
        is_complete = False

        def awaiting_closing_answer(self):
            return not self.is_complete

        def close_on_silence(self):
            self.is_complete = True
            return phrase("identification.silence_goodbye")

    engine = EngineProcessor(Session(), StandaloneTurns(), SpokenTracker())
    pushed = []

    async def push(frame, *_a):
        pushed.append(frame)

    engine.push_frame = push

    async def go():
        engine.create_task = lambda coro: asyncio.get_running_loop().create_task(coro)
        await engine._checkin()
        await engine._hangup_task

    asyncio.run(go())
    said = [f.text for f in pushed if isinstance(f, LLMTextFrame)]
    assert said == [phrase("identification.silence_goodbye")]
    assert isinstance(pushed[-1], EndWorkerFrame)
