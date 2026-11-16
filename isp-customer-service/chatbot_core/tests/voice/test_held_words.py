"""Words said over the agent are kept (Andrius 2026-11-16): without barge-in the agent
finishes its phrase, and what the caller said over it is not lost — live, „trisdešimt
devyni" over „kokią sumą?" was dropped and had to be said again."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pipecat")

from agent.barge_in import held_words_count  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    BotStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402

FUNCTION = "Žodžiai per agentą"

SUM_ASKED = "Ačiū. Dar pasakykite — kokią sumą?"
NEWS = "Patikrinau — paslauga sustabdyta dėl neapmokėtų sąskaitų. Skola 49 eurai 98 centai."


class TestTheEngineDecides:
    @pytest.mark.parametrize("said", ["39", "Taip, pavyko.", "Butas trys"])
    def test_over_a_question_the_words_are_its_answer(self, said):
        assert held_words_count(said, agent_asked=True)

    @pytest.mark.parametrize(
        "said",
        [
            "Aš mokėjau liepą",  # a payment
            "39 eurus",  # a number
            "Nesutinku su ta skola",  # a dispute
            "Palaukit",  # a halt word
        ],
    )
    def test_over_a_statement_a_fact_counts(self, said):
        assert held_words_count(said, agent_asked=False)

    @pytest.mark.parametrize("said", ["Mhm.", "A.", "Aha, va.", "Labas."])
    def test_a_listening_sound_answers_no_question(self, said):
        # Records 2026-11: „Mhm.", „A." over „…Ar registruoti?" — not a „taip".
        assert not held_words_count(said, agent_asked=True)

    @pytest.mark.parametrize("said", ["Taip.", "Gerai.", "Jo."])
    def test_a_yes_still_answers_it(self, said):
        assert held_words_count(said, agent_asked=True)

    @pytest.mark.parametrize("said", ["Visos sveikas!", "Geriausiai laukiam.", ""])
    def test_over_a_statement_a_stray_phrase_does_not(self, said):
        # The TV, someone in the room: not a turn.
        assert not held_words_count(said, agent_asked=False)


class Tracker:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def agent_asked(self) -> bool:
        return self.reply.rstrip().endswith("?")

    def question_is_yes_no(self) -> bool:
        return False


class Gate:
    def __init__(self) -> None:
        self.busy = True  # the agent is speaking


class Session:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.asr_context = lambda: ""

        class Tracer:
            def emit(_self, kind, **fields):
                self.events.append((kind, fields))

        self.tracer = Tracer()


def wav(secs: float = 1.0) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes(int(secs * 8000) * 2))
    return buf.getvalue()


class Call:
    def __init__(self, monkeypatch, reply: str, *texts: str) -> None:
        from app.call_audio import RawCallTrack
        from app.pipecat_call import EngineSTT

        monkeypatch.setenv("BARGE_IN", "0")
        monkeypatch.setenv("ASR_WHOLE_TURN", "on")

        async def passthrough(*_a, **_k):
            return None

        monkeypatch.setattr(
            "pipecat.services.stt_service.SegmentedSTTService.process_frame", passthrough
        )
        said = list(texts)

        class Asr:
            def transcribe(self, *_a, **_k):
                return said.pop(0)

        self.gate = Gate()
        self.session = Session()
        recorder = type("R", (), {"caller": lambda *_a: None, "raw": RawCallTrack(None, "x")})()
        self.stt = EngineSTT(self.session, Asr(), recorder, self.gate, Tracker(reply))
        self.stt.HELD_WAIT_SECS = 0.01
        self.stt.start_processing_metrics = passthrough
        self.stt.stop_processing_metrics = passthrough
        self.pushed: list = []
        self.heard: list[str] = []

        async def push(frame, direction=FrameDirection.DOWNSTREAM):
            self.pushed.append(frame)

        self.stt.push_frame = push

    async def frame(self, frame) -> None:
        await self.stt.process_frame(frame, FrameDirection.UPSTREAM)

    async def say(self) -> None:
        """One segment: VAD start and stop, then its transcript."""
        await self.frame(VADUserStartedSpeakingFrame())
        await self.frame(VADUserStoppedSpeakingFrame())
        async for f in self.stt.run_stt(wav()):
            self.heard.append(f.text)

    async def agent_stops(self) -> None:
        self.gate.busy = False
        await self.frame(BotStoppedSpeakingFrame())

    def held(self) -> list[tuple[str, bool]]:
        from app.pipecat_call import HeldWordsFrame

        return [(f.text, f.asked) for f in self.pushed if isinstance(f, HeldWordsFrame)]

    def verdicts(self) -> list[str]:
        return [f["verdict"] for k, f in self.session.events if k == "barge_in"]


class TestWordsOverTheAgentAreKept:
    def test_an_answer_over_the_question_reaches_the_engine_when_the_agent_stops(self, monkeypatch):
        call = Call(monkeypatch, SUM_ASKED, "Trisdešimt devyni.")

        async def go():
            await call.say()  # over the agent: not a turn of its own
            assert call.heard == [] and call.held() == []
            await call.agent_stops()
            await asyncio.sleep(0.05)

        asyncio.run(go())
        assert call.verdicts() == ["held"]
        assert call.held() == [("39.", True)]

    def test_when_the_caller_goes_on_the_kept_words_open_the_turn(self, monkeypatch):
        call = Call(monkeypatch, SUM_ASKED, "Trisdešimt devyni.", "eurų, grynais.")

        async def go():
            await call.say()
            await call.agent_stops()
            await call.say()  # within the wait: the caller goes on
            await asyncio.sleep(0.05)

        asyncio.run(go())
        assert call.held() == []
        assert call.heard == ["39. eurų, grynais."]

    def test_a_backchannel_over_a_statement_is_not_kept(self, monkeypatch):
        call = Call(monkeypatch, NEWS, "Mhm.")

        async def go():
            await call.say()
            await call.agent_stops()
            await asyncio.sleep(0.05)

        asyncio.run(go())
        assert call.verdicts() == ["ignored"] and call.held() == []

    def test_our_own_words_heard_back_are_not_kept(self, monkeypatch):
        call = Call(monkeypatch, NEWS, "Paslauga sustabdyta dėl neapmokėtų sąskaitų.")

        async def go():
            await call.say()
            await call.agent_stops()
            await asyncio.sleep(0.05)

        asyncio.run(go())
        assert call.verdicts() == ["ignored"] and call.held() == []

    def test_words_wait_while_the_agent_still_speaks(self, monkeypatch):
        call = Call(monkeypatch, SUM_ASKED, "Trisdešimt devyni.")

        async def go():
            await call.say()
            await asyncio.sleep(0.05)  # the agent is still speaking: nothing yet
            assert call.held() == []
            await call.agent_stops()
            await asyncio.sleep(0.05)

        asyncio.run(go())
        assert call.held() == [("39.", True)]


def test_the_engine_answers_kept_words_it_takes(monkeypatch):
    """`EngineProcessor`: a HeldWordsFrame the engine takes starts a reply; one it does not
    take is only traced."""
    from unittest.mock import MagicMock

    from app.pipecat_call import EngineProcessor, HeldWordsFrame

    session = MagicMock(is_complete=False)
    engine = EngineProcessor(session, MagicMock(), MagicMock(), MagicMock(), MagicMock())
    replies: list[str] = []

    async def reply(text, _previous):
        replies.append(text)

    engine._reply = reply
    engine.create_task = lambda coro: asyncio.get_event_loop().create_task(coro)

    async def noop(*_a, **_k):
        return None

    engine._disarm_checkin = noop

    async def go():
        await engine.process_frame(HeldWordsFrame(text="39", asked=True), FrameDirection.DOWNSTREAM)
        await engine.process_frame(
            HeldWordsFrame(text="Visos sveikas!", asked=False), FrameDirection.DOWNSTREAM
        )
        await asyncio.sleep(0)

    monkeypatch.setattr("pipecat.processors.frame_processor.FrameProcessor.process_frame", noop)
    asyncio.run(go())
    assert replies == ["39"]
    taken = [
        c.kwargs["taken"] for c in session.tracer.emit.call_args_list if c.args[0] == "held_words"
    ]
    assert taken == [True, False]
