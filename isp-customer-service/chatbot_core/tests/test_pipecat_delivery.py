"""Pipecat voice: after a barge-in the engine hears what the caller actually heard (D1)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pipecat")

from app.pipecat_call import EngineProcessor, SpokenTracker, StandaloneTurns  # noqa: E402

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


def test_the_caller_starts_a_turn_by_voice_only_while_the_agent_is_silent():
    from app.pipecat_call import QuietVADUserTurnStartStrategy
    from pipecat.frames.frames import (
        BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
    )
    from pipecat.turns.types import ProcessFrameResult

    started = []
    strategy = QuietVADUserTurnStartStrategy()

    async def trigger(*_args, **_kwargs):
        started.append(True)

    strategy.trigger_user_turn_started = trigger

    async def run():
        await strategy.process_frame(BotStartedSpeakingFrame())
        speaking = await strategy.process_frame(VADUserStartedSpeakingFrame())
        await strategy.process_frame(BotStoppedSpeakingFrame())
        silent = await strategy.process_frame(VADUserStartedSpeakingFrame())
        return speaking, silent

    speaking, silent = asyncio.run(run())
    assert speaking == ProcessFrameResult.CONTINUE  # a bare word does not cut the agent off
    assert silent == ProcessFrameResult.STOP
    assert started == [True]
