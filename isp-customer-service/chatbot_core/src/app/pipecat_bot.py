"""Pipecat spike — the same engine behind Pipecat's voice layer (ROADMAP A1, B4).

Pipecat does the call around the engine: WebRTC in the browser, Silero VAD, Smart Turn v3
(end-of-turn from the voice), interruptions and audio pacing. What stays ours: the
`AgentSession` (every decision and reply), Groq ASR with the Lithuanian prompt and the
agent's last question as context, number normalisation and the noise filter, and Piper
with our Lithuanian phonemizer.

    uv run python chatbot_core/src/app/pipecat_bot.py -t webrtc
    → open http://localhost:7860/client

Env: PIPECAT_CALLER (caller-ID of the demo call, default the first dashboard scenario),
SMART_TURN_STOP_SECS (silence fallback when Smart Turn says “not finished”, default 2.0),
VAD_STOP_SECS (pause that triggers a Smart Turn check, default 0.2).

Not in the spike: barge-in delivery report (what part of the reply was heard), check-ins,
the dashboard. Each turn's user→bot latency is written to the call trace as `pipecat_latency`.
"""

from __future__ import annotations

import asyncio
import functools
import os
import sys
import threading
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_SHARED = _SRC.parents[1] / "shared" / "src"
if _SHARED.exists() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
try:
    from utils import load_env

    load_env()
except Exception:
    pass

from loguru import logger  # noqa: E402
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams  # noqa: E402
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3  # noqa: E402
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.audio.vad.vad_analyzer import VADParams  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
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
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.worker import PipelineParams, PipelineWorker  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments  # noqa: E402
from pipecat.services.settings import STTSettings, TTSSettings  # noqa: E402
from pipecat.services.stt_service import SegmentedSTTService  # noqa: E402
from pipecat.services.tts_service import TTSService  # noqa: E402
from pipecat.transports.base_transport import TransportParams  # noqa: E402
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport  # noqa: E402
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (  # noqa: E402
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies  # noqa: E402
from pipecat.utils.time import time_now_iso8601  # noqa: E402

DEFAULT_CALLER = "+37060020101"


class EngineSTT(SegmentedSTTService):
    """Our Groq ASR on each VAD segment: Lithuanian domain prompt + the agent's last
    question as context, numbers normalised, noise dropped (as `voice_pipeline`)."""

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
    """Piper with our Lithuanian phonemizer and recipe, sentence by sentence as PCM."""

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


class EngineProcessor(FrameProcessor):
    """Stands where an LLM service would: the user's finished turn in, the engine's
    reply out as LLM text frames (the TTS splits it into sentences)."""

    def __init__(self, session, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session = session
        self._task = None
        self._stop = threading.Event()
        self._turn_lock = asyncio.Lock()

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

    async def greet(self) -> None:
        text = await asyncio.to_thread(self._session.greeting)
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
        async with self._turn_lock:
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


@functools.lru_cache(maxsize=1)
def _startup():
    """What the dashboard app does before its first call: config, knowledge, ASR, TTS —
    once per process, Piper warmed (its first sentence loads the model, ~6 s)."""
    from agent.contract import loader
    from app import runtime_config
    from app.voice import _build_asr, _build_tts

    runtime_config.load_persisted()
    loader.startup()
    tts = _build_tts()
    if not hasattr(tts, "synthesize_pcm"):
        raise RuntimeError("The Pipecat spike needs Piper (TTS_ENGINE=piper) for PCM output.")
    tts.synthesize_pcm("Labas.")
    return _build_asr(), tts


async def bot(runner_args: RunnerArguments):
    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        raise RuntimeError("Run with -t webrtc")
    from agent import AgentSession

    asr, tts_provider = await asyncio.to_thread(_startup)
    session = AgentSession(caller_phone=os.environ.get("PIPECAT_CALLER", DEFAULT_CALLER))
    session.use_background_analyst()
    session.tracer.emit("transport", name="pipecat", version="1.12.0")

    transport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    stt = EngineSTT(session, asr)
    engine = EngineProcessor(session)
    tts = EnginePiperTTS(session, tts_provider)

    context = LLMContext()
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
    user_agg, assistant_agg = LLMContextAggregatorPair(context, user_params=user_params)

    pipeline = Pipeline(
        [transport.input(), stt, user_agg, engine, tts, transport.output(), assistant_agg]
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
        await engine.greet()

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client):
        await asyncio.to_thread(session.end_session, "client_closed")
        await worker.cancel()

    from pipecat.workers.runner import WorkerRunner

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:  # the agent hung up, or the browser left — the finalizer runs once
        await asyncio.to_thread(session.end_session, "pipeline_end")


if __name__ == "__main__":
    from pipecat.runner.run import main

    # The runner's banner uses box-drawing characters a Windows cp1252 console cannot print.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    _startup()  # before the first browser connects, not during its greeting
    main()
