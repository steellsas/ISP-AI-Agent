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
2.0), VAD_STOP_SECS (pause that triggers a Smart Turn check, default 0.2).

Not yet: the barge-in delivery report (what part of the reply was heard) and check-ins.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import time

from loguru import logger
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    EndWorkerFrame,
    ErrorFrame,
    Frame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
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
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.time import time_now_iso8601


class EngineSTT(SegmentedSTTService):
    """Our ASR on each VAD segment: Lithuanian domain prompt + the agent's last question
    as context, numbers normalised, noise dropped (as `voice_pipeline`)."""

    def __init__(self, session, asr, **kwargs) -> None:
        super().__init__(settings=STTSettings(model=None, language=None), **kwargs)
        self._session = session
        self._asr = asr

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes):
        from adapters.asr.lt_text import is_asr_noise, normalize_lt_numbers

        await self.start_processing_metrics()
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

    def __init__(self, session, provider, **kwargs) -> None:
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=TTSSettings(model=None, voice=None, language=None),
            **kwargs,
        )
        self._session = session
        self._provider = provider

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

        async def phrases():
            nonlocal size
            yield first[0]
            while (piece := await asyncio.to_thread(next, pieces, None)) is not None:
                size += len(piece[0])
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


class StandaloneTurns:
    """Turn bookkeeping when nothing else owns the session (`pipecat_bot.py`)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def turn(self):
        async with self._lock:
            yield

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

    async def call_ended(self) -> None:
        self._ms.session.tracer.emit("call_ended", transport="pipecat")


class EngineProcessor(FrameProcessor):
    """Stands where an LLM service would: the user's finished turn in, the engine's
    reply out as LLM text frames (the TTS splits it into sentences)."""

    def __init__(self, session, turns, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._turns = turns
        self._task = None
        self._stop = threading.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            text = _last_user_text(frame.context)
            if text:
                await self._cancel()
                self._task = self.create_task(self._reply(text))
        elif isinstance(frame, InterruptionFrame):
            if self._task is not None:
                self._session.request_cancel()
            await self._cancel()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def say(self, text: str) -> None:
        """Speak text the engine already produced (the greeting)."""
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(text))
        await self.push_frame(LLMFullResponseEndFrame())

    async def _cancel(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self.cancel_task(self._task)
            self._task = None
        self._stop = threading.Event()

    async def _reply(self, text: str) -> None:
        stop = self._stop
        async with self._turns.turn():
            tokens = self._session.handle_turn_stream(text)
            await self.push_frame(LLMFullResponseStartFrame())
            await self.start_ttfb_metrics()
            try:
                while not stop.is_set():
                    token = await asyncio.to_thread(next, tokens, None)
                    if token is None:
                        break
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
    """The pipeline for one call; returns its worker. `greeting=None` asks the engine for
    one when the browser connects; a string is spoken as is (the dashboard made it)."""
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    engine = EngineProcessor(session, turns)
    user_params = LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(
            params=VADParams(stop_secs=float(os.environ.get("VAD_STOP_SECS", "0.2")))
        ),
        user_turn_strategies=UserTurnStrategies(
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(
                        params=SmartTurnParams(
                            stop_secs=float(os.environ.get("SMART_TURN_STOP_SECS", "2.0"))
                        )
                    )
                )
            ]
        ),
    )
    user_agg, assistant_agg = LLMContextAggregatorPair(LLMContext(), user_params=user_params)
    pipeline = Pipeline(
        [
            transport.input(),
            EngineSTT(session, asr),
            user_agg,
            engine,
            EnginePiperTTS(session, tts_provider),
            transport.output(),
            assistant_agg,
        ]
    )

    latency = UserBotLatencyObserver()

    @latency.event_handler("on_latency_breakdown")
    async def _on_breakdown(_observer, breakdown):
        parts = {c.key: round(c.duration_secs * 1000) for c in breakdown.contributions}
        session.tracer.emit(
            "pipecat_latency",
            total_ms=round(breakdown.total_secs * 1000),
            user_turn_ms=round((breakdown.user_turn_secs or 0) * 1000),
            parts=parts,
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
    return worker


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
    worker = build_call(
        connection, ms.session, asr, tts, DashboardTurns(ms, manager, session_id), ms.greeting
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
