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
    greeting: str = ""  # the opening line (the Pipecat call speaks it on connect)
    # F-3: open call sockets, and the pending end once the last one closed.
    sockets: int = 0
    pending_end: asyncio.Task | None = None


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
        # One checkpoint saver for every session in the process, opened on first
        # use and closed on shutdown.
        self._checkpointer = None

    def _saver(self):
        if self._checkpointer is None:
            from agent.graph_v2.checkpoint import make_checkpointer

            self._checkpointer = make_checkpointer(self._settings.checkpoint_path)
        return self._checkpointer

    # --- lifecycle ----------------------------------------------------------

    async def create(self, caller_phone: str = "unknown") -> dict[str, Any]:
        def _start() -> tuple[AgentSession, str]:
            session = AgentSession(caller_phone=caller_phone, checkpointer=self._saver())
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
    def hub(self) -> SessionEventHub:
        """The live event hub (the Pipecat call writes its turn summaries through it)."""
        return self._hub

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

    def socket_opened(self, session_id: str) -> None:
        """A call socket connected: a pending disconnect end is called off (F-3)."""
        ms = self.get(session_id)
        ms.sockets += 1
        if ms.pending_end is not None and not ms.pending_end.done():
            ms.pending_end.cancel()
            logger.info(f"session {session_id}: socket reconnected, end called off")
        ms.pending_end = None

    def socket_closed(self, session_id: str) -> None:
        """A call socket closed: when it was the last one, the call ends after the grace
        unless the client comes back (F-3 — the record must not wait for the TTL)."""
        ms = self._sessions.get(session_id)
        if ms is None:
            return  # already ended (hang-up DELETE)
        ms.sockets = max(0, ms.sockets - 1)
        if ms.sockets == 0 and ms.pending_end is None:
            ms.pending_end = asyncio.create_task(
                self._end_after_grace(session_id, self._settings.ws_disconnect_grace_seconds)
            )

    async def _end_after_grace(self, session_id: str, grace: float) -> None:
        await asyncio.sleep(grace)
        ms = self._sessions.get(session_id)
        if ms is None or ms.sockets > 0:
            return
        ms.pending_end = None  # the end itself must not cancel this task
        with suppress(SessionNotFound):
            await self.end(session_id, outcome="ws_disconnect")

    async def end(self, session_id: str, outcome: str = "client_closed") -> None:
        ms = self._sessions.pop(session_id, None)
        if ms is None:
            raise SessionNotFound(session_id)
        if ms.pending_end is not None and not ms.pending_end.done():
            ms.pending_end.cancel()
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
        from agent.graph_v2.checkpoint import close_checkpointer

        close_checkpointer(self._checkpointer)
        self._checkpointer = None
