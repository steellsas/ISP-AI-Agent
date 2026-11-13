"""The turn heard whole (ASR_WHOLE_TURN): a pause inside a sentence no longer makes Whisper
hear "Mano vardas yra" and "Tomas." apart — each segment is heard with the turn so far, and
that text replaces the turn's earlier one (noise bench 2026-11-13: CER 33 % → 23 %)."""

from __future__ import annotations

import asyncio
import io
import wave

import pytest

pytest.importorskip("pipecat")

from pipecat.frames.frames import (  # noqa: E402
    BotStartedSpeakingFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402

FUNCTION = "Visas ėjimas į ASR"

RATE = 8000


def segment(secs: float, level: int = 1000) -> bytes:
    """A VAD segment as Pipecat hands it over: speech, then 0.5 s of padded silence."""
    speech = int(secs * RATE)
    pcm = (level.to_bytes(2, "little", signed=True)) * speech + bytes(int(0.5 * RATE) * 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def secs_of(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / w.getframerate()


class Asr:
    """Says what it is told to, and keeps how long each audio it heard was."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.heard: list[float] = []

    def transcribe(self, audio, **_k):
        self.heard.append(round(secs_of(audio), 2))
        return self.texts.pop(0)


class Gate:
    def __init__(self) -> None:
        self.busy = False


class Session:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.asr_context = lambda: ""

        class Tracer:
            def emit(_self, kind, **fields):
                self.events.append((kind, fields))

        self.tracer = Tracer()


class Call:
    """EngineSTT alone: VAD frames in, run_stt on each segment, transcripts out."""

    def __init__(self, monkeypatch, *texts: str, whole: str = "on", barge: str = "0") -> None:
        from app.call_audio import RawCallTrack
        from app.pipecat_call import EngineSTT

        monkeypatch.setenv("ASR_WHOLE_TURN", whole)
        monkeypatch.setenv("BARGE_IN", barge)

        async def passthrough(*_a, **_k):
            return None

        monkeypatch.setattr(
            "pipecat.services.stt_service.SegmentedSTTService.process_frame", passthrough
        )
        self.asr = Asr(*texts)
        self.gate = Gate()
        self.session = Session()
        recorder = type("R", (), {"caller": lambda *_a: None, "raw": RawCallTrack(None, "x")})()
        self.stt = EngineSTT(self.session, self.asr, recorder, self.gate)
        self.stt.start_processing_metrics = passthrough
        self.stt.stop_processing_metrics = passthrough
        self.frames: list[TranscriptionFrame] = []

    def frame(self, frame) -> None:
        asyncio.run(self.stt.process_frame(frame, FrameDirection.UPSTREAM))

    def say(self, secs: float, *, over_agent: bool = False) -> None:
        self.gate.busy = over_agent
        self.frame(VADUserStartedSpeakingFrame())
        self.frame(VADUserStoppedSpeakingFrame())
        self.gate.busy = False

    def hear(self, secs: float) -> list[TranscriptionFrame]:
        async def go():
            return [f async for f in self.stt.run_stt(segment(secs))]

        out = asyncio.run(go())
        self.frames += out
        return out

    def piece(self, secs: float, **kw) -> list[TranscriptionFrame]:
        self.say(secs, **kw)
        return self.hear(secs)


def replaces(frames) -> list[int]:
    return [f.result["replaces"] for f in frames]


class TestTheTurnIsHeardWhole:
    def test_the_second_piece_is_heard_with_the_first(self, monkeypatch):
        call = Call(monkeypatch, "Mano vardas yra", "Mano vardas yra Tomas.")
        call.piece(1.0)
        call.piece(0.5)
        # alone: 1.0 s + 0.5 s pad; then both pieces + one pad
        assert call.asr.heard == [1.5, 2.0]
        assert [f.text for f in call.frames] == ["Mano vardas yra", "Mano vardas yra Tomas."]
        assert replaces(call.frames) == [0, 1]

    def test_every_later_piece_replaces_the_one_text_the_turn_has(self, monkeypatch):
        call = Call(monkeypatch, "Taip", "Taip, dėl", "Taip, dėl Tilžės 60.")
        for secs in (0.5, 0.5, 1.0):
            call.piece(secs)
        assert call.asr.heard == [1.0, 1.5, 2.5]
        assert replaces(call.frames) == [0, 1, 1]

    def test_a_new_turn_starts_afresh(self, monkeypatch):
        call = Call(monkeypatch, "Tomas.", "Taip.")
        call.piece(1.0)
        call.frame(UserStoppedSpeakingFrame())  # Smart Turn: the turn is over
        call.piece(0.5)
        assert call.asr.heard == [1.5, 1.0]
        assert replaces(call.frames) == [0, 0]

    def test_the_agent_speaking_ends_the_turn(self, monkeypatch):
        call = Call(monkeypatch, "Tomas.", "Taip.")
        call.piece(1.0)
        call.frame(BotStartedSpeakingFrame())
        call.piece(0.5)
        assert replaces(call.frames) == [0, 0]

    def test_the_turn_is_counted_when_queued_not_when_heard(self, monkeypatch):
        # Pipecat transcribes later, in order: the turn may have ended before a piece said
        # in it is heard — it still belongs to its own turn.
        call = Call(monkeypatch, "Mano vardas", "Mano vardas Tomas.")
        call.say(1.0)
        call.say(0.5)
        call.frame(UserStoppedSpeakingFrame())
        call.hear(1.0)
        call.hear(0.5)
        assert replaces(call.frames) == [0, 1]


class TestWhatNeverJoinsATurn:
    def test_words_wholly_over_the_agent_stay_out(self, monkeypatch):
        call = Call(monkeypatch, "Mhm.", "Tomas.")
        call.piece(0.5, over_agent=True)  # dropped, as before
        call.piece(1.0)
        assert [f.text for f in call.frames] == ["Tomas."]
        assert call.asr.heard == [1.0, 1.5]  # the "mhm" was never added to the turn
        assert replaces(call.frames) == [0]

    def test_a_noise_piece_does_not_start_the_turn(self, monkeypatch):
        call = Call(monkeypatch, "", "Tomas.", "Tomas, taip.")
        call.piece(0.5)  # nothing readable: dropped
        call.piece(1.0)
        call.piece(0.5)
        assert call.asr.heard == [1.0, 1.5, 2.0]
        assert replaces(call.frames) == [0, 1]

    def test_a_noisy_whole_turn_leaves_the_last_good_text(self, monkeypatch):
        call = Call(monkeypatch, "Tomas.", "")
        call.piece(1.0)
        assert call.piece(0.5) == []  # the aggregator keeps "Tomas."

    def test_a_very_long_turn_starts_over_and_adds(self, monkeypatch):
        from app.pipecat_call import EngineSTT

        monkeypatch.setattr(EngineSTT, "MAX_TURN_SECS", 2.0)
        call = Call(monkeypatch, "Pirma.", "Pirma, antra.", "Trečia.")
        for secs in (1.0, 0.8, 1.0):
            call.piece(secs)
        assert replaces(call.frames) == [0, 1, 0]

    def test_off_every_piece_is_heard_alone(self, monkeypatch):
        call = Call(monkeypatch, "Mano vardas yra", "Tomas.", whole="off")
        call.piece(1.0)
        call.piece(0.5)
        assert call.asr.heard == [1.5, 1.0]
        assert replaces(call.frames) == [0, 0]


class TestTheAggregatorKeepsTheWholeTurn:
    def aggregator(self):
        from app.pipecat_call import WholeTurnUserAggregator
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import (
            LLMContextAggregatorPair,
        )

        user, _ = LLMContextAggregatorPair(LLMContext())
        user.__class__ = WholeTurnUserAggregator
        return user

    def feed(self, user, *said: tuple[str, int]) -> str:
        async def go():
            for text, rep in said:
                f = TranscriptionFrame(text, "", "", result={"replaces": rep})
                await user._handle_transcription(f)
            return user.aggregation_string()

        return asyncio.run(go())

    def test_the_turn_text_replaces_its_pieces(self):
        user = self.aggregator()
        got = self.feed(user, ("Mano vardas yra", 0), ("Mano vardas yra Tomas.", 1))
        assert got == "Mano vardas yra Tomas."

    def test_a_new_turn_text_is_added(self):
        user = self.aggregator()
        assert self.feed(user, ("Pirma.", 0), ("Trečia.", 0)) == "Pirma. Trečia."

    def test_never_removes_more_than_it_holds(self):
        user = self.aggregator()
        assert self.feed(user, ("Tomas.", 3)) == "Tomas."

    def test_the_call_uses_it(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.pipecat_call import WholeTurnUserAggregator, build_call

        monkeypatch.setenv("API_RECORD_AUDIO", "0")
        session = MagicMock(session_id="whole-turn")
        worker, recorder = build_call(MagicMock(), session, MagicMock(), MagicMock(), [], "")
        recorder.close()

        def walk(p):
            yield p
            for child in getattr(p, "_processors", []):
                yield from walk(child)

        users = [p for p in walk(worker._pipeline) if isinstance(p, WholeTurnUserAggregator)]
        assert len(users) == 1
