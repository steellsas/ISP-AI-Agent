"""Per-session live event hub — tracer sink → WebSocket subscribers.

The engine's tracer already emits everything the demo "brain" panel needs
(node, tool_call/result + ms, rag, decision, scripted, llm tokens/latency).
This hub is a thin fan-out: a tracer sink pushes each event into every
subscriber's asyncio.Queue. Turns run in worker threads (the engine is sync),
so publishing hops to the event loop via call_soon_threadsafe.

It also keeps a per-session ring buffer of recent events — the source the
SessionManager slices per turn to build the `turn_summary`.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_BUFFER_MAX = 2000  # per session; a long call emits a few hundred events


class SessionEventHub:
    """Fan-out of tracer events to live subscribers, keyed by session_id."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._buffers: dict[str, deque] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup — the loop the queues live on."""
        self._loop = loop

    # --- producer side (tracer sink, runs in worker threads) ---------------

    def make_sink(self, session_id: str):
        """A tracer sink bound to one session (attach via tracer.add_sink)."""
        self._buffers.setdefault(session_id, deque(maxlen=_BUFFER_MAX))

        def _sink(event: dict) -> None:
            self.publish(session_id, event)

        return _sink

    def publish(self, session_id: str, event: dict) -> None:
        """Thread-safe: buffer the event and push it to live subscribers."""
        buf = self._buffers.setdefault(session_id, deque(maxlen=_BUFFER_MAX))
        buf.append(event)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for q in list(self._subscribers.get(session_id, [])):
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:  # pragma: no cover - loop shutting down
                return

    # --- consumer side (WebSocket / SSE handlers, event loop) --------------

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id)
        if subs and q in subs:
            subs.remove(q)

    # --- turn bookkeeping ---------------------------------------------------

    def mark(self, session_id: str) -> int:
        """Current buffer position — snapshot before a turn."""
        return len(self._buffers.get(session_id, ()))

    def events_since(self, session_id: str, mark: int) -> list[dict[str, Any]]:
        """Events emitted after `mark` (this turn's slice)."""
        buf = self._buffers.get(session_id)
        if buf is None:
            return []
        return list(buf)[mark:]

    def drop(self, session_id: str) -> None:
        """Session ended — free the buffer, wake subscribers with a sentinel."""
        self._buffers.pop(session_id, None)
        loop = self._loop
        for q in self._subscribers.pop(session_id, []):
            if loop is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(q.put_nowait, None)
                except RuntimeError:  # pragma: no cover
                    pass
