"""Pipecat voice: the agent finishes its phrase, then decides who speaks (PERZIURA §6 I-3)."""

from __future__ import annotations

import asyncio

import pytest

ASKED = "Patikrinau — paslauga sustabdyta. Ar registruoti?"
NEWS = "Patikrinau — paslauga sustabdyta dėl neapmokėtų sąskaitų."


@pytest.mark.parametrize(
    "said, agent_text, asked, decision",
    [
        ("", NEWS, False, "continue"),  # nothing readable
        ("aha", NEWS, False, "continue"),  # backchannel
        ("Oho, oho.", NEWS, False, "continue"),  # live 2026-10-19
        ("Laukiu.", NEWS, False, "continue"),  # live 2026-10-19: cut the debt news
        ("Patikrinau paslauga sustabdyta", NEWS, False, "continue"),  # our own echo
        ("Ne, palaukit", NEWS, False, "yield"),  # a halt word, at any length
        ("Aš mokėjau liepos mėnesį", NEWS, False, "yield"),  # content
        ("Labas", NEWS, False, "yield"),  # a greeting takes the turn (I-1 re-delivers)
        ("Gerai, ačiū.", ASKED, True, "yield"),  # G17: the answer over the question
        ("Taip.", ASKED, True, "yield"),
        # G1: an answer repeats the question's words — not echo
        (
            "Lemputė nedega su interneto simboliu",
            "Ar lemputė su interneto simboliu dega?",
            True,
            "yield",
        ),
    ],
)
def test_who_takes_the_turn(said, agent_text, asked, decision):
    from agent.barge_in import overlap_decision

    assert overlap_decision(said, agent_text, asked) == decision


pytest.importorskip("pipecat")


class FakeGate:
    def __init__(self, busy: bool) -> None:
        self.busy = busy
        self.calls: list[str] = []

    def finish_then_hold(self):
        self.calls.append("hold")

    def release(self):
        self.calls.append("release")

    def drop(self):
        self.calls.append("drop")


class FakeTracker:
    def __init__(self, reply: str, asked: bool) -> None:
        self.reply = reply
        self._asked = asked

    def agent_asked(self):
        return self._asked


class FakeSession:
    def __init__(self) -> None:
        self.events = []

        class Tracer:
            def emit(_self, kind, **fields):
                self.events.append((kind, fields.get("verdict")))

        self.tracer = Tracer()


def run_strategy(gate, tracker, said):
    from app.pipecat_call import FinishThenDecideUserTurnStartStrategy
    from pipecat.frames.frames import (
        TranscriptionFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )

    session = FakeSession()
    strategy = FinishThenDecideUserTurnStartStrategy(gate, tracker, session)
    started = []

    async def trigger(*_a, **_k):
        started.append(True)

    strategy.trigger_user_turn_started = trigger

    async def go():
        first = await strategy.process_frame(VADUserStartedSpeakingFrame())
        await strategy.process_frame(VADUserStoppedSpeakingFrame())
        last = await strategy.process_frame(TranscriptionFrame(said, "caller", "now"))
        return first, last

    first, last = asyncio.run(go())
    return first, last, started, session.events


def test_while_the_agent_is_silent_the_voice_starts_the_turn():
    from pipecat.turns.types import ProcessFrameResult

    gate = FakeGate(busy=False)
    first, _, started, _ = run_strategy(gate, FakeTracker(NEWS, False), "Neveikia internetas")
    assert first == ProcessFrameResult.STOP and started == [True] and gate.calls == []


def test_a_backchannel_lets_the_agent_go_on_from_where_it_stopped():
    gate = FakeGate(busy=True)
    _, _, started, events = run_strategy(gate, FakeTracker(NEWS, False), "aha")
    assert gate.calls == ["hold", "release"] and started == []
    assert events == [("barge_in", "continue")]


def test_an_answer_over_the_question_takes_the_turn():
    from pipecat.turns.types import ProcessFrameResult

    gate = FakeGate(busy=True)
    _, last, started, events = run_strategy(gate, FakeTracker(ASKED, True), "Gerai, ačiū.")
    assert gate.calls == ["hold", "drop"] and started == [True]
    assert last == ProcessFrameResult.STOP and events == [("barge_in", "yield")]


def test_the_question_playing_now_counts_as_asked():
    from app.pipecat_call import SpokenTracker

    t = SpokenTracker()
    t.reply = "Supratau, lemputės nedega. Ar laidas tvirtai įkištas?"
    t.spoken = ["Supratau, lemputės nedega."]
    assert t.agent_asked()
    t.spoken = []
    assert not t.agent_asked()  # still on the first sentence


def test_the_gate_stops_at_the_phrase_pause_and_goes_on_after_release():
    """Paced out; on a caller's word it lets the phrase finish, holds at its pause, and
    on release plays the rest — nothing is lost."""
    import numpy as np
    from app.pipecat_call import PacedHoldGate
    from pipecat.frames.frames import TTSAudioRawFrame

    rate = 24000
    voiced = (np.ones(int(rate * 0.3)) * 3000).astype(np.int16).tobytes()
    pause = np.zeros(int(rate * 0.2), dtype=np.int16).tobytes()
    phrase2 = (np.ones(int(rate * 0.3)) * 3000).astype(np.int16).tobytes()

    gate = PacedHoldGate()
    out: list[bytes] = []

    async def push(frame, *_a):
        if isinstance(frame, TTSAudioRawFrame):
            out.append(frame.audio)

    gate.push_frame = push
    gate.create_task = lambda coro: asyncio.get_running_loop().create_task(coro)

    async def go():
        from pipecat.processors.frame_processor import FrameDirection

        frame = TTSAudioRawFrame(voiced + pause + phrase2, rate, 1)
        # process_frame's base bookkeeping needs a running pipeline: enqueue directly
        gate._enqueue_audio(frame)
        gate._pump = asyncio.get_running_loop().create_task(gate._run())
        gate._wake.set()
        await asyncio.sleep(0.05)
        gate.finish_then_hold()  # the caller spoke during the first phrase
        await asyncio.sleep(0.8)
        held_at = sum(len(a) for a in out)
        gate.release()
        await asyncio.sleep(0.8)
        gate._pump.cancel()
        return held_at, sum(len(a) for a in out), FrameDirection

    held_at, total, _ = asyncio.run(go())
    assert len(voiced) <= held_at < len(voiced) + len(pause)  # stopped at the pause
    assert total == len(voiced) + len(pause) + len(phrase2)  # and nothing was lost
