"""Pipecat call without the dashboard — Pipecat's own test page (ROADMAP A1, B4).

    uv run python chatbot_core/src/app/pipecat_bot.py -t webrtc
    → open http://localhost:7860/client

The call itself is `pipecat_call.build_call`, the same one the dashboard runs. Here the
session is made per browser connection and ended when it leaves.

Env: PIPECAT_CALLER (caller-ID of the call, default the first dashboard scenario), and the
turn-detection knobs listed in `pipecat_call`.
"""

from __future__ import annotations

import asyncio
import functools
import os
import sys
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

from app.pipecat_call import StandaloneTurns, build_call  # noqa: E402
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments  # noqa: E402

DEFAULT_CALLER = "+37060020101"


@functools.lru_cache(maxsize=1)
def _startup():
    """What the dashboard app does before its first call: config, knowledge, ASR, TTS —
    once per process, Piper warmed."""
    from agent.contract import loader
    from app import runtime_config
    from app.voice import _build_asr, _build_tts

    runtime_config.load_persisted()
    loader.startup()
    tts = _build_tts()
    if not hasattr(tts, "stream_pcm"):
        raise RuntimeError("Pipecat voice needs Piper (TTS_ENGINE=piper) for PCM output.")
    tts.synthesize_pcm("Labas.")
    return _build_asr(), tts


async def bot(runner_args: RunnerArguments):
    if not isinstance(runner_args, SmallWebRTCRunnerArguments):
        raise RuntimeError("Run with -t webrtc")
    from agent import AgentSession
    from pipecat.workers.runner import WorkerRunner

    asr, tts = await asyncio.to_thread(_startup)
    session = AgentSession(caller_phone=os.environ.get("PIPECAT_CALLER", DEFAULT_CALLER))
    session.use_background_analyst()
    worker, recorder = build_call(
        runner_args.webrtc_connection, session, asr, tts, StandaloneTurns(), greeting=None
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:  # the agent hung up, or the browser left — the finalizer runs once
        recorder.close()
        await asyncio.to_thread(session.end_session, "client_closed")


if __name__ == "__main__":
    from pipecat.runner.run import main

    # The runner's banner uses box-drawing characters a Windows cp1252 console cannot print.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    _startup()  # before the first browser connects, not during its greeting
    main()
