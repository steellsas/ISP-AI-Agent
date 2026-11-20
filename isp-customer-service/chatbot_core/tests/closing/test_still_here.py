"""Dar čia (#82 — live 2026-11-20): the closing question got no answer, the agent said its
silence goodbye, the caller asked „Ką reikia daryti?" over it — and the line went down. The
silence goodbye is the engine's guess that the caller is gone; their words prove it wrong.
"""

import asyncio

import pytest
from agent.contract.locale import phrase

FUNCTION = "Dar čia"


def test_the_session_opens_again_after_the_silence_goodbye():
    from agent import AgentSession

    session = AgentSession(caller_phone="+37060020101")
    session._state.dialog.last_question = "Ar dar kuo galiu padėti?"
    session.close_on_silence()
    assert session.is_complete
    session.reopen_after_silence_goodbye()
    assert not session.is_complete


pytest.importorskip("pipecat")


class _Tracer:
    def emit(self, *_a, **_k):
        pass


class _Session:
    tracer = _Tracer()

    def __init__(self):
        self.is_complete = False
        self.reopened = False

    def awaiting_closing_answer(self):
        return not self.is_complete

    def awaiting_caller(self):
        return False

    def close_on_silence(self):
        self.is_complete = True
        return phrase("identification.silence_goodbye")

    def reopen_after_silence_goodbye(self):
        self.is_complete = False
        self.reopened = True


def _over_the_goodbye(monkeypatch, words):
    from app.pipecat_call import EngineProcessor, HeldWordsFrame, SpokenTracker, StandaloneTurns
    from pipecat.frames.frames import EndWorkerFrame

    monkeypatch.setenv("CLOSING_SILENCE_S", "0")
    monkeypatch.setenv("GOODBYE_HANGUP_S", "0.3")
    session = _Session()
    engine = EngineProcessor(session, StandaloneTurns(), SpokenTracker())
    pushed, replies = [], []

    async def push(frame, *_a):
        pushed.append(frame)

    async def reply(text, _previous):
        replies.append(text)

    engine.push_frame = push
    engine._reply = reply

    async def go():
        loop = asyncio.get_running_loop()
        engine.create_task = lambda coro: loop.create_task(coro)

        async def cancel(task):
            task.cancel()

        engine.cancel_task = cancel
        await engine._checkin()  # the silence goodbye; the hang-up is pending
        await asyncio.sleep(0.05)
        await _feed(engine, HeldWordsFrame(text=words, asked=False))
        await asyncio.sleep(0.5)  # past the hang-up pause

    asyncio.run(go())
    return session, replies, any(isinstance(f, EndWorkerFrame) for f in pushed)


async def _feed(engine, frame):
    """The engine's own reading of held words, without the base processor's setup."""
    from app.pipecat_call import EngineProcessor

    real = EngineProcessor.__mro__[1].process_frame

    async def skip(*_a, **_k):
        return None

    EngineProcessor.__mro__[1].process_frame = skip
    try:
        await engine.process_frame(frame, None)
    finally:
        EngineProcessor.__mro__[1].process_frame = real


def test_words_over_the_silence_goodbye_keep_the_line_up(monkeypatch):
    session, replies, hung_up = _over_the_goodbye(monkeypatch, "Ką reikia daryti?")
    assert session.reopened and not hung_up
    assert replies == ["Ką reikia daryti?"]


def test_a_goodbye_over_it_lets_the_line_go_down(monkeypatch):
    session, replies, hung_up = _over_the_goodbye(monkeypatch, "Ačiū, viso gero")
    assert not session.reopened and hung_up and not replies
