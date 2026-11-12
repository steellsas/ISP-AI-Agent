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


def test_the_call_end_waits_for_the_turn_still_running(session):
    """Live 2026-11-05: a hang-up during the last turn finalized the state from before that
    turn and registered a second ticket. The end now waits for the turn."""
    import threading
    import time

    ended = threading.Event()
    session._turn_running.acquire()  # a turn is running
    worker = threading.Thread(target=lambda: (session.end_session("client_closed"), ended.set()))
    worker.start()
    time.sleep(0.3)
    assert not ended.is_set()
    session._turn_running.release()  # the turn finished
    worker.join(5)
    assert ended.is_set()


def test_a_task_silence_hears_hold_on_before_the_checkin(monkeypatch):
    """2026-11-11: 35 s of silence while the caller does a task sounds like a dropped line — a
    short „neskubėkite, aš čia" first, the „kaip sekasi?" only later."""
    from app.pipecat_call import EngineProcessor, SpokenTracker, StandaloneTurns
    from pipecat.frames.frames import LLMTextFrame

    monkeypatch.setenv("VOICE_HOLD_AFTER_S", "1")
    monkeypatch.setenv("VOICE_CHECKIN_AFTER_S", "2")

    class Tracer:
        def emit(self, *_a, **_k):
            pass

    class Session:
        is_complete = False
        tracer = Tracer()

        def awaiting_closing_answer(self):
            return False

        def awaiting_caller(self):
            return True

    tracker = SpokenTracker()
    tracker.reply = "Įjunkite telefone Wi-Fi."
    engine = EngineProcessor(Session(), StandaloneTurns(), tracker)
    pushed = []

    async def push(frame, *_a):
        pushed.append(frame)

    engine.push_frame = push

    async def go():
        await engine._checkin()  # the hold, then this task ends (speaking disarms it)
        await engine._checkin()  # the next silence: the check-in

    asyncio.run(go())
    said = [f.text for f in pushed if isinstance(f, LLMTextFrame)]
    assert said == [phrase("identification.hold_on"), phrase("identification.checkin")]
