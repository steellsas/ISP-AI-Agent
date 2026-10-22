"""Pipecat voice: after a barge-in the engine hears what the caller actually heard (D1)."""

from __future__ import annotations

import asyncio

import pytest
from app.pipecat_call import EngineProcessor, SpokenTracker, StandaloneTurns  # noqa: E402

FUNCTION = "Ką išgirdo klientas"

pytest.importorskip("pipecat")


REPLY = "Supratau — lemputės nedega. Patikrinkime maitinimą. Ar laidas tvirtai įkištas?"


def tracker(spoken: list[str], reply: str = REPLY) -> SpokenTracker:
    t = SpokenTracker()
    t.reply = reply
    t.spoken = spoken
    return t


def test_nothing_unheard_when_every_sentence_played():
    assert (
        tracker(
            ["Supratau — lemputės nedega.", "Patikrinkime maitinimą.", "Ar laidas tvirtai įkištas?"]
        ).unheard()
        == ""
    )


def test_the_tail_after_the_played_sentences_is_unheard():
    assert tracker(["Supratau — lemputės nedega."]).unheard() == (
        "Patikrinkime maitinimą. Ar laidas tvirtai įkištas?"
    )


def test_whitespace_from_the_tts_aggregator_does_not_matter():
    t = tracker(["Supratau —  lemputės nedega."], reply=REPLY.replace(" — ", " —\n"))
    assert t.unheard().startswith("Patikrinkime")


def test_nothing_played_means_the_whole_reply_is_unheard():
    assert tracker([]).unheard() == REPLY


class FakeSession:
    def __init__(self) -> None:
        self.delivered = None

    def apply_delivery(self, sentences, delivered):
        self.delivered = (sentences, delivered)


def test_the_engine_gets_heard_sentences_and_the_unheard_tail():
    session = FakeSession()
    engine = EngineProcessor(session, StandaloneTurns(), tracker(["Supratau — lemputės nedega."]))
    asyncio.run(engine._report_delivery(None))
    assert session.delivered == (
        ["Supratau — lemputės nedega.", "Patikrinkime maitinimą. Ar laidas tvirtai įkištas?"],
        1,
    )


def test_a_fully_heard_reply_reports_nothing():
    session = FakeSession()
    played = [
        "Supratau — lemputės nedega.",
        "Patikrinkime maitinimą.",
        "Ar laidas tvirtai įkištas?",
    ]
    engine = EngineProcessor(session, StandaloneTurns(), tracker(played))
    asyncio.run(engine._report_delivery(None))
    assert session.delivered is None


def test_the_call_audio_is_recorded_turn_by_turn(tmp_path, monkeypatch):
    """V1: the archive plays a Pipecat call — the old voice path's file names."""
    import io
    import json
    import wave

    from app.pipecat_call import CallRecorder

    monkeypatch.setenv("API_RECORD_DIR", str(tmp_path))

    def wav(frames: int) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x01\x00" * frames)
        return buf.getvalue()

    rec = CallRecorder("call-1", enabled=True)
    rec.agent(b"\x00\x00" * 100, 22050)  # the greeting
    rec.caller(wav(160))
    rec.caller(wav(160))  # two VAD segments of one turn
    rec.next_turn()  # the first reply starts
    rec.agent(b"\x00\x00" * 50, 22050)
    rec.interrupted()
    rec.close()

    d = tmp_path / "call-1"
    names = sorted(p.name for p in d.iterdir())
    assert names == ["manifest.jsonl", "turn_00_agent.wav", "turn_01_agent.wav", "turn_01_user.wav"]
    with wave.open(str(d / "turn_01_user.wav")) as w:
        assert w.getnframes() == 320 and w.getframerate() == 16000
    manifest = [json.loads(line) for line in (d / "manifest.jsonl").read_text().splitlines()]
    assert manifest[-1] == {**manifest[-1], "side": "agent", "cancelled": True}


class CheckinSession(FakeSession):
    def __init__(self, waiting: bool) -> None:
        super().__init__()
        self.waiting = waiting
        self.is_complete = False
        self.events = []

        class Tracer:
            def emit(_self, kind, **fields):
                self.events.append(kind)

        self.tracer = Tracer()

    def awaiting_caller(self):
        return self.waiting

    def awaiting_closing_answer(self):
        return False


@pytest.mark.parametrize("waiting, spoken", [(True, True), (False, False)])
def test_a_silent_caller_with_a_task_gets_one_checkin(monkeypatch, waiting, spoken):
    from pipecat.frames.frames import LLMTextFrame

    monkeypatch.setenv("VOICE_CHECKIN_AFTER_S", "0")
    session = CheckinSession(waiting)
    engine = EngineProcessor(session, StandaloneTurns(), tracker([]))
    pushed = []

    async def push(frame, *_args):
        pushed.append(frame)

    engine.push_frame = push
    asyncio.run(engine._checkin())
    said = [f.text for f in pushed if isinstance(f, LLMTextFrame)]
    assert bool(said) is spoken
    assert ("checkin" in session.events) is spoken


def test_the_engine_turn_runs_in_one_thread_so_its_context_scope_closes():
    """F3 (live 2026-10-20): pulled token by token through asyncio.to_thread, the session's
    ContextVar scope failed to close and the reply task died at every turn's end."""
    import contextvars

    from app.pipecat_call import _in_one_thread

    var = contextvars.ContextVar("scope", default=None)

    def turn():
        token = var.set("call-1")
        try:
            yield "Gerai. "
            yield "Kas toliau?"
        finally:
            var.reset(token)  # raises if the steps ran in different contexts

    async def collect():
        return [t async for t in _in_one_thread(turn)]

    assert asyncio.run(collect()) == ["Gerai. ", "Kas toliau?"]


def test_silence_after_a_question_gets_a_shorter_different_checkin(monkeypatch):
    """F4: after a question the caller has nothing to do — silence means they may not hear."""
    from agent.contract.locale import phrase
    from pipecat.frames.frames import LLMTextFrame

    monkeypatch.setenv("VOICE_CHECKIN_QUESTION_S", "0")
    monkeypatch.setenv("VOICE_CHECKIN_AFTER_S", "60")  # would hang the test if used
    session = CheckinSession(True)
    t = tracker([], reply="Tuoj patikrinsiu ryšį. O su kuo kalbu — koks jūsų vardas?")
    engine = EngineProcessor(session, StandaloneTurns(), t)
    pushed = []

    async def push(frame, *_args):
        pushed.append(frame)

    engine.push_frame = push
    asyncio.run(engine._checkin())
    said = [f.text for f in pushed if isinstance(f, LLMTextFrame)]
    assert said == [phrase("identification.checkin_question")]
