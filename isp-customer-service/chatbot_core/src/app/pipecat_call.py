"""One call through Pipecat's voice layer — shared by the dashboard and `pipecat_bot.py`.

Pipecat does the call around the engine: WebRTC audio, Silero VAD, Smart Turn v3
(end-of-turn from the voice), interruptions and audio pacing. What stays ours: the
`AgentSession` (every decision and reply), Groq ASR with the Lithuanian prompt and the
agent's last question as context, number normalisation and the noise filter, and Piper
with our Lithuanian phonemizer (in its worker pool).

In the dashboard (`run_dashboard_call`) the session is the one `POST /sessions` made, so
the brain panel, the archive and the simulate buttons see this call like any other: every
turn runs under the session lock and ends with the same `turn_summary`.

Env: SMART_TURN_STOP_SECS (silence fallback when Smart Turn says “not finished”, default
1.2 — 2.0 left a caller waiting 1.5 s after a finished “Ne, …”, DELSA §5.4), VAD_STOP_SECS (pause that triggers a Smart Turn check, default 0.2).

After a barge-in the engine hears which sentences were played out (`SpokenTracker`), as on
the old voice path. Not yet: check-ins.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import os
import threading
import time

from agent.barge_in import overlap_decision
from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndWorkerFrame,
    ErrorFrame,
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    SystemFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSTextFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.services.tts_service import TTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_start.base_user_turn_start_strategy import BaseUserTurnStartStrategy
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.time import time_now_iso8601


class CallRecorder:
    """The call's audio, turn by turn, where the old voice path kept it: the caller's
    `turn_NN_user.wav` and the agent's `turn_NN_agent.wav` in `logs/sessions/<id>/`, with
    `manifest.jsonl` — so the archive plays a Pipecat call and the offline tools
    (`smart_turn_eval.py`) read it. The greeting is `turn_00_agent.wav`. Off with
    API_RECORD_AUDIO=0."""

    def __init__(self, session_id: str, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = os.environ.get("API_RECORD_AUDIO", "1") != "0"
        self.enabled = enabled
        self._sid = session_id
        self._turn = 0
        self._caller = bytearray()
        self._caller_rate = 16000
        self._agent = bytearray()
        self._agent_rate = 22050
        self._cancelled = False

    def caller(self, wav: bytes) -> None:
        """One VAD segment (a WAV container) of the caller's speech."""
        if not self.enabled:
            return
        import io
        import wave

        try:
            with wave.open(io.BytesIO(wav)) as w:
                self._caller_rate = w.getframerate()
                self._caller += w.readframes(w.getnframes())
        except Exception:  # pragma: no cover - a recording never breaks a call
            logger.debug("caller segment not recorded", exc_info=True)

    def agent(self, pcm: bytes, rate: int) -> None:
        if self.enabled:
            self._agent_rate = rate
            self._agent += pcm

    def interrupted(self) -> None:
        self._cancelled = True

    def next_turn(self) -> None:
        """A reply starts: the previous agent audio and this turn's caller audio go to disk."""
        self._write_agent()
        self._turn += 1
        if self._caller:
            self._write(
                f"turn_{self._turn:02d}_user.wav", self._caller, self._caller_rate, "caller"
            )
        self._caller = bytearray()

    def close(self) -> None:
        self._write_agent()
        if self._caller:  # the caller spoke after the last reply (a goodbye over the hang-up)
            self._turn += 1
            self._write(
                f"turn_{self._turn:02d}_user.wav", self._caller, self._caller_rate, "caller"
            )
            self._caller = bytearray()

    def _write_agent(self) -> None:
        if self._agent:
            extra = {"cancelled": True} if self._cancelled else {}
            self._write(
                f"turn_{self._turn:02d}_agent.wav", self._agent, self._agent_rate, "agent", **extra
            )
        self._agent = bytearray()
        self._cancelled = False

    def _write(self, name: str, pcm: bytearray, rate: int, side: str, **extra) -> None:
        if not self.enabled:
            return
        import wave

        from .voice import _manifest, _record_dir

        try:
            d = _record_dir(self._sid)
            d.mkdir(parents=True, exist_ok=True)
            with wave.open(str(d / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(bytes(pcm))
            _manifest(d, side, name, **extra)
        except Exception:  # pragma: no cover - a recording never breaks a call
            logger.warning(f"audio recording failed: {name}", exc_info=True)


class EngineSTT(SegmentedSTTService):
    """Our ASR on each VAD segment: Lithuanian domain prompt + the agent's last question
    as context, numbers normalised, noise dropped (as `voice_pipeline`)."""

    def __init__(self, session, asr, recorder: CallRecorder, **kwargs) -> None:
        super().__init__(settings=STTSettings(model=None, language=None), **kwargs)
        self._session = session
        self._asr = asr
        self._recorder = recorder

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes):
        from adapters.asr.lt_text import is_asr_noise, normalize_lt_numbers

        await self.start_processing_metrics()
        self._recorder.caller(audio)
        t0 = time.perf_counter()
        context = self._session.asr_context()
        try:
            raw = await asyncio.to_thread(
                self._asr.transcribe, audio, language="lt", context=context
            )
        except Exception as exc:  # pragma: no cover - provider trouble
            yield ErrorFrame(error=f"ASR failed: {exc}")
            return
        await self.stop_processing_metrics()
        text = normalize_lt_numbers(raw or "")
        dropped = not text or is_asr_noise(text)
        self._session.tracer.emit(
            "asr",
            raw=raw,
            transcript=text,
            ms=round((time.perf_counter() - t0) * 1000),
            dropped=dropped,
            context=context or "",
            transport="pipecat",
        )
        if not dropped:
            yield TranscriptionFrame(text, self._user_id, time_now_iso8601())


class EnginePiperTTS(TTSService):
    """Piper with our Lithuanian phonemizer and recipe, phrase by phrase as PCM."""

    def __init__(self, session, provider, recorder: CallRecorder, **kwargs) -> None:
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model=None, voice=None, language=None),
            **kwargs,
        )
        self._session = session
        self._provider = provider
        self._recorder = recorder

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str):
        await self.start_tts_usage_metrics(text)
        t0 = time.perf_counter()
        pieces = self._provider.stream_pcm(text)
        first = await asyncio.to_thread(next, pieces, None)
        first_ms = round((time.perf_counter() - t0) * 1000)
        if first is None:
            await self.stop_ttfb_metrics()
            return
        sample_rate = first[1]
        size = len(first[0])
        self._recorder.agent(first[0], sample_rate)

        async def phrases():
            nonlocal size
            yield first[0]
            while (piece := await asyncio.to_thread(next, pieces, None)) is not None:
                size += len(piece[0])
                self._recorder.agent(piece[0], sample_rate)
                yield piece[0]

        async for frame in self._stream_audio_frames_from_iterator(
            phrases(), in_sample_rate=sample_rate, context_id=context_id
        ):
            await self.stop_ttfb_metrics()
            yield frame
        # `ms` = the first phrase (what the caller waits for); `all_ms` = the sentence
        self._session.tracer.emit(
            "tts",
            ms=first_ms,
            all_ms=round((time.perf_counter() - t0) * 1000),
            chars=len(text),
            bytes=size,
        )


class PacedHoldGate(FrameProcessor):
    """Between the TTS and the audio output: the agent's audio goes out at speaking pace
    (a quarter second ahead of the speaker, not the whole reply at once), so the agent can
    stop at the end of its current phrase and go on from there (PERZIURA §6 I-3).

    open       audio flows at speaking pace
    finishing  the caller spoke: the current phrase plays out up to its pause (the recipe's
               silence after a comma or a full stop), at most `barge_finish_max_ms`
    held       nothing more goes out; `release()` goes on from here, `drop()` (or a barge-in
               interruption) throws the rest away
    """

    CHUNK_S = 0.04
    LEAD_S = 0.25
    SILENT_RMS = 60.0

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._queue: collections.deque = collections.deque()
        self._wake = asyncio.Event()
        self._state = "open"
        self._deadline = 0.0
        self._out_until = 0.0  # when the audio already handed to the output ends
        self._pump = None

    @property
    def busy(self) -> bool:
        """The agent is speaking, or holds speech it may still say."""
        return bool(self._queue) or self._state != "open" or time.monotonic() < self._out_until

    def finish_then_hold(self) -> None:
        from agent.contract import limits

        if self._state == "open" and self.busy:
            self._state = "finishing"
            self._deadline = time.monotonic() + limits.get("barge_finish_max_ms") / 1000
            self._wake.set()

    def release(self) -> None:
        self._state = "open"
        self._wake.set()

    def drop(self) -> None:
        self._queue.clear()
        self._state = "open"
        self._out_until = time.monotonic()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            self.drop()
            await self.push_frame(frame, direction)
            return
        if direction != FrameDirection.DOWNSTREAM or isinstance(frame, SystemFrame):
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TTSAudioRawFrame):
            self._enqueue_audio(frame)
        elif self._queue:
            self._queue.append(frame)  # keeps its place behind the audio (TTSTextFrame timing)
        else:
            await self.push_frame(frame, direction)
            return
        if self._pump is None:
            self._pump = self.create_task(self._run())
        self._wake.set()

    def _enqueue_audio(self, frame: TTSAudioRawFrame) -> None:
        step = int(frame.sample_rate * self.CHUNK_S) * 2 * frame.num_channels
        audio = frame.audio
        for i in range(0, len(audio), step):
            self._queue.append(
                TTSAudioRawFrame(
                    audio[i : i + step],
                    frame.sample_rate,
                    frame.num_channels,
                    context_id=getattr(frame, "context_id", None),
                )
            )

    def _silent(self, frame: TTSAudioRawFrame) -> bool:
        import numpy as np

        pcm = np.frombuffer(frame.audio, dtype=np.int16)
        if pcm.size == 0:
            return True
        return float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) < self.SILENT_RMS

    async def _run(self) -> None:
        while True:
            if not self._queue or self._state == "held":
                self._wake.clear()
                await self._wake.wait()
                continue
            frame = self._queue[0]
            if isinstance(frame, TTSAudioRawFrame):
                now = time.monotonic()
                if self._state == "finishing" and (self._silent(frame) or now >= self._deadline):
                    self._state = "held"  # the phrase is over: the agent stops here
                    continue
                lead = self._out_until - now
                if lead > self.LEAD_S:
                    self._wake.clear()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._wake.wait(), lead - self.LEAD_S)
                    continue
                self._queue.popleft()
                duration = len(frame.audio) / (2 * frame.num_channels * frame.sample_rate)
                self._out_until = max(self._out_until, now) + duration
                await self.push_frame(frame)
            else:
                self._queue.popleft()
                await self.push_frame(frame)


class FinishThenDecideUserTurnStartStrategy(BaseUserTurnStartStrategy):
    """Who takes the turn when the caller speaks (PERZIURA §6 I-3).

    The agent is silent: the caller's voice starts the turn at once (VAD).
    The agent is speaking: it finishes its phrase and holds (`PacedHoldGate`); once the
    caller's words are transcribed, `agent.barge_in.overlap_decision` decides: an answer, a
    question, a halt -> the caller's turn (and the D1 report of what they heard); a
    backchannel, our own echo, nothing readable -> the agent goes on from where it stopped.
    No words within `barge_wait_transcript_ms` after the caller stops -> it goes on too."""

    def __init__(self, gate: PacedHoldGate, tracker: SpokenTracker, session, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gate = gate
        self._tracker = tracker
        self._session = session
        self._pending = False
        self._timer = None

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, VADUserStartedSpeakingFrame):
            if self._gate.busy:
                self._pending = True
                self._cancel_timer()
                self._gate.finish_then_hold()
                return ProcessFrameResult.CONTINUE
            await self.trigger_user_turn_started()
            return ProcessFrameResult.STOP
        if isinstance(frame, VADUserStoppedSpeakingFrame) and self._pending:
            self._cancel_timer()
            self._timer = asyncio.create_task(self._give_up())
        elif isinstance(frame, TranscriptionFrame) and self._pending:
            self._pending = False
            self._cancel_timer()
            asked = self._tracker.agent_asked()
            decision = overlap_decision(frame.text, self._tracker.reply, asked)
            self._session.tracer.emit(
                "barge_in",
                verdict=decision,
                transcript=frame.text,
                asked=asked,
                transport="pipecat",
            )
            if decision == "yield":
                self._gate.drop()
                await self.trigger_user_turn_started()
                return ProcessFrameResult.STOP
            self._gate.release()
        return ProcessFrameResult.CONTINUE

    async def _give_up(self) -> None:
        from agent.contract import limits

        await asyncio.sleep(limits.get("barge_wait_transcript_ms") / 1000)
        if self._pending:  # the caller made a sound, not words
            self._pending = False
            self._session.tracer.emit(
                "barge_in", verdict="continue", transcript="", transport="pipecat"
            )
            self._gate.release()

    def _cancel_timer(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
        self._timer = None


class StandaloneTurns:
    """Turn bookkeeping when nothing else owns the session (`pipecat_bot.py`)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def turn(self):
        async with self._lock:
            yield

    def locked(self):
        """Write between turns (the delivery report) without counting a turn."""
        return self._lock

    async def call_ended(self) -> None:
        return None


class DashboardTurns:
    """Turn bookkeeping for a dashboard session: the session lock, activity for the idle
    sweep, `turn_start` for the brain panel, the same `turn_summary` as every other turn."""

    def __init__(self, ms, manager, session_id: str) -> None:
        self._ms = ms
        self._manager = manager
        self._sid = session_id

    @contextlib.asynccontextmanager
    async def turn(self):
        from .sessions import build_turn_summary

        ms, hub = self._ms, self._manager.hub
        async with ms.lock:
            ms.last_activity = time.monotonic()
            mark = hub.mark(self._sid)
            ms.session.tracer.emit("turn_start", transport="pipecat")
            t0 = time.perf_counter()
            try:
                yield
            finally:
                wall_ms = int((time.perf_counter() - t0) * 1000)
                ms.turn_count += 1
                ms.last_activity = time.monotonic()
                summary = build_turn_summary(hub.events_since(self._sid, mark), wall_ms)
                ms.session.tracer.emit("turn_summary", **summary)

    def locked(self):
        """Write between turns (the delivery report) without counting a turn."""
        return self._ms.lock

    async def call_ended(self) -> None:
        self._ms.session.tracer.emit("call_ended", transport="pipecat")


class SpokenTracker(FrameProcessor):
    """After the audio output: which sentences of the current reply the caller actually
    heard. A TTS service without word timestamps queues each sentence's `TTSTextFrame`
    behind that sentence's audio, so it passes here once the sentence has been played
    out — the Pipecat twin of the old voice path's “played N chunks” count (D1)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.reply = ""
        self.spoken: list[str] = []

    def start(self) -> None:
        self.reply = ""
        self.spoken = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSTextFrame) and frame.text.strip():
            self.spoken.append(frame.text.strip())
        await self.push_frame(frame, direction)

    def agent_asked(self) -> bool:
        """Has the agent asked a question in this reply - one already played out, or the
        sentence playing now? Then any words from the caller are an answer."""
        import re

        if any("?" in sentence for sentence in self.spoken):
            return True
        current = re.split(r"(?<=[.!?])\s+", self.unheard(), maxsplit=1)[0]
        return current.rstrip().endswith("?")

    def unheard(self) -> str:
        """The part of the reply after the sentences played out ('' = heard it all).
        Whitespace is compared folded: the TTS aggregator joins tokens its own way."""
        reply = " ".join(self.reply.split())
        pos = 0
        for sentence in self.spoken:
            sentence = " ".join(sentence.split())
            at = reply.find(sentence, pos)
            if at < 0:
                break
            pos = at + len(sentence)
        return reply[pos:].strip()


class EngineProcessor(FrameProcessor):
    """Stands where an LLM service would: the user's finished turn in, the engine's
    reply out as LLM text frames (the TTS splits it into sentences).

    On an interruption the reply's remaining words are no longer spoken, but the engine's
    turn still runs to its end (it closes the LLM stream itself on `request_cancel`): an
    abandoned turn would leave the graph's last step unsaved. Then the engine is told
    what the caller actually heard (`apply_delivery`), as on the old voice path."""

    def __init__(
        self, session, turns, tracker: SpokenTracker, recorder: CallRecorder | None = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._turns = turns
        self._tracker = tracker
        self._recorder = recorder or CallRecorder("", enabled=False)
        self._task = None
        self._delivery_task = None
        self._stop = threading.Event()
        self._checkin_task = None
        self._checked_in = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStoppedSpeakingFrame):
            self._arm_checkin()
        elif isinstance(frame, (BotStartedSpeakingFrame, LLMContextFrame, InterruptionFrame)):
            await self._disarm_checkin()
        if isinstance(frame, LLMContextFrame):
            text = _last_user_text(frame.context)
            if text:
                self._task = self.create_task(self._reply(text, self._task))
        elif isinstance(frame, InterruptionFrame):
            self._stop.set()  # the running reply (if any) stops speaking
            if self._task is not None and not self._task.done():
                self._session.request_cancel()
            if self._delivery_task is None or self._delivery_task.done():
                self._delivery_task = self.create_task(self._report_delivery(self._task))
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def say(self, text: str) -> None:
        """Speak text the engine already produced (the greeting)."""
        self._tracker.start()
        self._tracker.reply = text
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(text))
        await self.push_frame(LLMFullResponseEndFrame())

    # The agent accompanies the caller through a task (G3, as the old voice path): after it
    # stops speaking, if the caller stays silent past `voice_checkin_after_s` while the engine
    # waits for them, it speaks first — „Kaip sekasi — ar pavyksta?". Once per turn.
    def _arm_checkin(self) -> None:
        if self._checked_in or os.getenv("VOICE_CHECKIN", "on").lower() != "on":
            return
        if self._task is None:  # not after the greeting — only once the caller has a task
            return
        if self._checkin_task is None or self._checkin_task.done():
            self._checkin_task = self.create_task(self._checkin())

    async def _disarm_checkin(self) -> None:
        if self._checkin_task is not None and not self._checkin_task.done():
            await self.cancel_task(self._checkin_task)
        self._checkin_task = None

    async def _checkin(self) -> None:
        from agent.contract import limits
        from agent.contract.locale import phrase

        await asyncio.sleep(float(limits.get("voice_checkin_after_s")))
        if self._session.is_complete or not self._session.awaiting_caller():
            return
        self._checked_in = True
        text = phrase("identification.checkin")
        self._session.tracer.emit("checkin", text=text, transport="pipecat")
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(text))
        await self.push_frame(LLMFullResponseEndFrame())

    async def _report_delivery(self, reply_task) -> None:
        """After an interruption — mid-turn or while the finished reply was still
        playing — tell the engine which sentences the caller heard."""
        if reply_task is not None and not reply_task.done():
            await reply_task  # the engine's turn drains first
        tail = self._tracker.unheard()
        if not tail:
            return
        self._recorder.interrupted()
        heard = list(self._tracker.spoken)
        async with self._turns.locked():
            await asyncio.to_thread(self._session.apply_delivery, [*heard, tail], len(heard))

    async def _reply(self, text: str, previous) -> None:
        for task in (previous, self._delivery_task):
            if task is not None and not task.done():
                await task  # one reply at a time; the last delivery report lands first
        stop = self._stop = threading.Event()
        self._checked_in = False
        self._tracker.start()
        self._recorder.next_turn()
        async with self._turns.turn():
            tokens = self._session.handle_turn_stream(text)
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_ttfb_metrics()
            try:
                while (token := await asyncio.to_thread(next, tokens, None)) is not None:
                    self._tracker.reply += token
                    if not stop.is_set():
                        await self.stop_ttfb_metrics()
                        await self.push_frame(LLMTextFrame(token))
            finally:
                await self.push_frame(LLMFullResponseEndFrame())
        if self._session.is_complete:
            # Let the goodbye play out, then hang up.
            await self._turns.call_ended()
            await self.push_frame(EndWorkerFrame())
            return
        # Between turns, as the voice transport does: fresh telemetry, the analyst.
        await asyncio.to_thread(self._between_turns)

    def _between_turns(self) -> None:
        try:
            self._session.refresh_telemetry_next()
            self._session.analyst_next()
        except Exception:  # pragma: no cover - background best-effort
            logger.exception("between-turn work failed")


def _last_user_text(context: LLMContext) -> str:
    for message in reversed(context.get_messages()):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
    return ""


def build_call(connection, session, asr, tts_provider, turns, greeting: str | None):
    """The pipeline for one call; returns its worker and the call's audio recorder (close it
    when the call ends). `greeting=None` asks the engine for one when the browser connects;
    a string is spoken as is (the dashboard made it)."""
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    tracker = SpokenTracker()
    gate = PacedHoldGate()
    recorder = CallRecorder(session.session_id)
    engine = EngineProcessor(session, turns, tracker, recorder)
    user_params = LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(
            params=VADParams(stop_secs=float(os.environ.get("VAD_STOP_SECS", "0.2")))
        ),
        user_turn_strategies=UserTurnStrategies(
            start=[FinishThenDecideUserTurnStartStrategy(gate, tracker, session)],
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(
                        params=SmartTurnParams(
                            stop_secs=float(os.environ.get("SMART_TURN_STOP_SECS", "1.2"))
                        )
                    )
                )
            ],
        ),
        # The greeting says the caller is talking to an AI (AI Act): it plays out whole.
        user_mute_strategies=[MuteUntilFirstBotCompleteUserMuteStrategy()],
    )
    user_agg, assistant_agg = LLMContextAggregatorPair(LLMContext(), user_params=user_params)
    pipeline = Pipeline(
        [
            transport.input(),
            EngineSTT(session, asr, recorder),
            user_agg,
            engine,
            EnginePiperTTS(session, tts_provider, recorder),
            gate,
            transport.output(),
            tracker,
            assistant_agg,
        ]
    )

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def _on_breakdown(_observer, breakdown):
        parts = {c.key: round(c.duration_secs * 1000) for c in breakdown.contributions}
        total_ms = round(breakdown.total_secs * 1000)
        session.tracer.emit(
            "pipecat_latency",
            total_ms=total_ms,
            user_turn_ms=round((breakdown.user_turn_secs or 0) * 1000),
            parts=parts,
            # After a barge-in the observer loses the turn start and measures from the call's
            # first request (G19: 19.8 s, 56 s, 97 s) — kept in the trace, left out of reports.
            suspect="first_request" in parts or "transcription" not in parts or total_ms > 15000,
        )
        logger.info(f"user→bot {breakdown.total_secs:.2f}s {parts}")

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        observers=[latency],
    )

    @transport.event_handler("on_client_connected")
    async def _on_connected(_transport, _client):
        text = greeting if greeting is not None else await asyncio.to_thread(session.greeting)
        await engine.say(text)

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client):
        await worker.cancel()

    session.tracer.emit("transport", name="pipecat")
    return worker, recorder


async def run_dashboard_call(connection, manager, session_id: str) -> None:
    """Run the Pipecat call of a dashboard session until the browser or the agent ends it.
    The session itself is ended by the dashboard (DELETE /sessions/{id}), as for every call."""
    from pipecat.workers.runner import WorkerRunner

    from .voice import _build_asr, _build_tts

    ms = manager.get(session_id)
    asr, tts = await asyncio.to_thread(lambda: (_build_asr(), _build_tts()))
    if not hasattr(tts, "stream_pcm"):
        raise RuntimeError("Pipecat voice needs Piper (TTS_ENGINE=piper)")
    ms.session.use_background_analyst()
    worker, recorder = build_call(
        connection, ms.session, asr, tts, DashboardTurns(ms, manager, session_id), ms.greeting
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        recorder.close()
