"""Session registry — one AgentSession per call, behind async endpoints.

The engine is sync (Phase 5 makes it async); every engine call runs in a
worker thread via asyncio.to_thread, and a per-session asyncio.Lock serializes
turns so two requests for the SAME call can never interleave. Different
sessions do not share anything — multi-call is structural; SCALE (threads,
rate limits, STT/TTS compute) is a Phase 5 concern by agreement.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from agent.session import AgentSession

from .config import ApiSettings, cost_usd
from .events import SessionEventHub

logger = logging.getLogger(__name__)


class SessionNotFound(KeyError):
    """Unknown or already-ended session_id."""


@dataclass
class ManagedSession:
    session: AgentSession
    caller_phone: str
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    turn_count: int = 0
    voice: Any = None  # VoicePipeline, attached lazily on the first audio frame
    greeting: str = ""  # the opening line (for the greeting-audio endpoint)
    # Barge-in (Phase 5 PR2): set by the WS reader when the caller interrupts —
    # the streaming turn stops SENDING further chunks immediately.
    interrupt: asyncio.Event = field(default_factory=asyncio.Event)
    # PR3: the ENGINE-side stop — checked between sentences in the worker
    # thread; closing the token stream stops the LLM generation itself and
    # triggers the engine's ask-rollback (threading.Event: cross-thread safe).
    cancel: threading.Event = field(default_factory=threading.Event)
    # E1 duplex: the latest rolling partial transcript of the utterance-so-far
    # (trace/display in E1; the E2 endpointer reads it for the turn-cut call).
    last_partial: str = ""
    # D1 delivery ledger: how many audio chunks the client reported as FULLY
    # played when it sent the interrupt (None = no report / no interrupt).
    interrupt_played: int | None = None
    # D2 duplex: the server-side audio front (VAD + endpoint authority),
    # attached lazily on the first FRAM frame.
    front: Any = None
    # Duplex-hearing: a SEPARATE front for speech spoken over the agent's
    # voice ("OVER" frames) — its segments become overlay observations,
    # never turns.
    overlay_front: Any = None


def build_turn_summary(events: list[dict[str, Any]], wall_ms: int) -> dict[str, Any]:
    """Compress one turn's trace slice into the dashboard's `turn_summary`:
    which node ran, ENGINE-vs-LLM authorship, tools + their ms, token/cost
    totals. Pure function over already-emitted events — no new engine state."""
    nodes: list[str] = []
    tools: list[dict[str, Any]] = []
    llm_calls = 0
    input_tokens = 0
    output_tokens = 0
    call_cost = 0.0
    model = None
    scripted = False
    pending_tool: str | None = None
    for e in events:
        t = e.get("type")
        if t == "node":
            node = e.get("node")
            if node and node not in nodes:
                nodes.append(node)
        elif t == "scripted":
            scripted = True
        elif t == "tool_call":
            pending_tool = e.get("name")
        elif t == "tool_result":
            tools.append(
                {"name": e.get("name") or pending_tool, "ok": e.get("ok"), "ms": e.get("ms")}
            )
            pending_tool = None
        elif t == "llm":
            llm_calls += 1
            model = e.get("model") or model
            input_tokens += int(e.get("input_tokens") or 0)
            output_tokens += int(e.get("output_tokens") or 0)
            call_cost += cost_usd(
                e.get("model"), int(e.get("input_tokens") or 0), int(e.get("output_tokens") or 0)
            )
    return {
        "nodes": nodes,
        "engine": "scripted" if scripted and not llm_calls else "llm",
        "tools": tools,
        "llm_calls": llm_calls,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(call_cost, 6),
        "latency_ms": wall_ms,
    }


class SessionManager:
    """Create / turn / end + TTL cleanup over the session registry."""

    def __init__(self, hub: SessionEventHub, settings: ApiSettings) -> None:
        self._hub = hub
        self._settings = settings
        self._sessions: dict[str, ManagedSession] = {}

    # --- lifecycle ----------------------------------------------------------

    async def create(self, caller_phone: str = "unknown") -> dict[str, Any]:
        def _start() -> tuple[AgentSession, str]:
            session = AgentSession(caller_phone=caller_phone)
            session.tracer.add_sink(self._hub.make_sink(session.session_id))
            return session, session.greeting()

        session, greeting = await asyncio.to_thread(_start)
        sid = session.session_id
        self._sessions[sid] = ManagedSession(
            session=session, caller_phone=caller_phone, greeting=greeting
        )
        logger.info(f"session created: {sid}")
        return {"session_id": sid, "greeting": greeting}

    def get(self, session_id: str) -> ManagedSession:
        ms = self._sessions.get(session_id)
        if ms is None:
            raise SessionNotFound(session_id)
        return ms

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    async def turn(self, session_id: str, text: str) -> dict[str, Any]:
        ms = self.get(session_id)
        async with ms.lock:
            ms.last_activity = time.monotonic()
            mark = self._hub.mark(session_id)
            t0 = time.perf_counter()
            reply = await asyncio.to_thread(ms.session.handle_turn, text)
            wall_ms = int((time.perf_counter() - t0) * 1000)
            ms.turn_count += 1
            ms.last_activity = time.monotonic()
            summary = build_turn_summary(self._hub.events_since(session_id, mark), wall_ms)
            # Through the tracer so it lands in the archive jsonl AND on the
            # live feed — one event pipeline, no side channel.
            ms.session.tracer.emit("turn_summary", **summary)
            return {
                "reply": reply,
                "turn": summary,
                "is_complete": ms.session.is_complete,
            }

    async def voice_turn(self, session_id: str, audio: bytes) -> tuple[dict[str, Any], bytes]:
        """One caller utterance (WAV bytes) -> (voice_turn payload + turn summary,
        reply audio). Same lock/summary discipline as text turns."""
        from . import voice  # lazy: keeps ASR/TTS adapter imports off the API import path

        ms = self.get(session_id)
        async with ms.lock:
            ms.last_activity = time.monotonic()
            mark = self._hub.mark(session_id)
            t0 = time.perf_counter()
            payload, reply_audio = await asyncio.to_thread(voice.run_voice_turn, ms, audio)
            wall_ms = int((time.perf_counter() - t0) * 1000)
            ms.turn_count += 1
            ms.last_activity = time.monotonic()
            summary = build_turn_summary(self._hub.events_since(session_id, mark), wall_ms)
            ms.session.tracer.emit("turn_summary", **summary)
            payload["turn"] = summary
            return payload, reply_audio

    async def voice_partial(self, session_id: str, audio: bytes) -> dict[str, Any] | None:
        """E1 duplex: rolling partial transcript of the utterance-so-far.
        Deliberately WITHOUT the session lock — a partial never touches engine
        state (ASR only), and taking the lock would delay the real turn behind
        an in-flight snapshot."""
        from . import voice  # lazy: keeps ASR/TTS adapter imports off the API import path

        ms = self.get(session_id)
        ms.last_activity = time.monotonic()
        return await asyncio.to_thread(voice.run_voice_partial, ms, audio)

    async def voice_overlay(self, session_id: str, audio: bytes) -> dict[str, Any] | None:
        """Duplex-hearing stage 1: transcribe + echo-filter speech spoken over
        the agent's voice. Observe-only — no lock, no engine state."""
        from . import voice  # lazy: keeps ASR/TTS adapter imports off the API import path

        ms = self.get(session_id)
        ms.last_activity = time.monotonic()
        return await asyncio.to_thread(voice.run_overlay, ms, audio)

    async def voice_turn_stream(
        self, session_id: str, audio: bytes, send_bytes, transcript: str | None = None
    ) -> dict[str, Any]:
        """Streaming voice turn (Phase 5 PR1): audio chunks are forwarded to
        `send_bytes` (an async callable, e.g. ws.send_bytes) AS THEY ARE
        SYNTHESIZED — the engine runs in a worker thread, chunks hop to the loop
        through a queue. Returns the done payload + turn summary."""
        from . import voice  # lazy: keeps ASR/TTS adapter imports off the API import path

        ms = self.get(session_id)
        async with ms.lock:
            ms.last_activity = time.monotonic()
            mark = self._hub.mark(session_id)
            loop = asyncio.get_running_loop()
            q: asyncio.Queue = asyncio.Queue()

            def on_chunk(b: bytes) -> None:  # worker thread -> loop
                loop.call_soon_threadsafe(q.put_nowait, b)

            t0 = time.perf_counter()
            # L3a (live 2026-08-14): capture the barge-in flag BEFORE clearing —
            # playback runs on wall-clock in the BROWSER, so the interruption
            # usually lands between server turns; sampling at the old turn's end
            # missed 9/10 interruptions and the classifier never ran.
            if ms.voice is not None:
                ms.voice.prev_cancelled = ms.cancel.is_set() or ms.interrupt.is_set()
            ms.interrupt.clear()
            ms.cancel.clear()
            task = asyncio.create_task(
                asyncio.to_thread(voice.run_voice_turn_stream, ms, audio, on_chunk, transcript)
            )
            task.add_done_callback(lambda _t: q.put_nowait(None))  # runs on the loop
            interrupted = False
            sent = 0
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                # Barge-in: the caller spoke over the reply — swallow the rest of
                # the chunks (the engine finishes in its thread; audio stops NOW).
                if ms.interrupt.is_set():
                    interrupted = True
                    continue
                await send_bytes(chunk)
                sent += 1
            payload = task.result()  # re-raises a worker failure
            payload["interrupted"] = interrupted
            payload["chunks_sent"] = sent
            # D1 delivery ledger: the client reported how many chunks finished
            # playing when it barged in — truncate the engine's history to the
            # heard prefix. Only when the pipeline's chunk<->sentence map is
            # trustworthy (no filler/fallback chunks); otherwise keep today's
            # assume-all-heard behaviour.
            if interrupted:
                played = ms.interrupt_played
                ms.interrupt_played = None
                sentences = list(getattr(ms.voice, "last_turn_sentences", None) or [])
                aligned = bool(getattr(ms.voice, "last_turn_aligned", False))
                if aligned and sentences and played is not None:
                    with suppress(Exception):  # a repair must never fail a turn
                        ms.session.apply_delivery(sentences, int(played))
            wall_ms = int((time.perf_counter() - t0) * 1000)
            ms.turn_count += 1
            ms.last_activity = time.monotonic()
            summary = build_turn_summary(self._hub.events_since(session_id, mark), wall_ms)
            ms.session.tracer.emit("turn_summary", **summary)
            payload["turn"] = summary
            return payload

    async def end(self, session_id: str, outcome: str = "client_closed") -> None:
        ms = self._sessions.pop(session_id, None)
        if ms is None:
            raise SessionNotFound(session_id)
        await asyncio.to_thread(ms.session.end_session, outcome)
        self._hub.drop(session_id)
        logger.info(f"session ended: {session_id} ({outcome})")

    async def expire_idle(self, min_idle_seconds: float) -> int:
        """End sessions idle for at least `min_idle_seconds` (proper session_end).
        Used by the DB reset so an abandoned tab cannot block it; the TTL loop
        remains the general sweep."""
        cutoff = time.monotonic() - min_idle_seconds
        ended = 0
        for sid, ms in list(self._sessions.items()):
            if ms.last_activity < cutoff and not ms.lock.locked():
                try:
                    await self.end(sid, outcome="expired")
                    ended += 1
                except Exception:  # pragma: no cover - defensive
                    logger.warning(f"expire_idle failed for {sid}", exc_info=True)
        return ended

    # --- TTL cleanup --------------------------------------------------------

    async def cleanup_loop(self) -> None:
        """Background task: end sessions idle past the TTL (proper session_end
        trace — a forgotten tab must not hold a call open forever)."""
        while True:
            await asyncio.sleep(self._settings.cleanup_interval_seconds)
            await self.expire_idle(self._settings.session_ttl_seconds)

    async def shutdown(self) -> None:
        for sid in list(self._sessions):
            try:
                await self.end(sid, outcome="server_shutdown")
            except Exception:  # pragma: no cover - defensive
                logger.warning(f"shutdown end failed for {sid}", exc_info=True)
