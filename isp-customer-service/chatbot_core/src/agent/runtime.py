"""
AgentRuntime — the per-call dependencies every graph node receives (D-01).

LangGraph hands it to nodes as `runtime.context` (StateGraph context_schema);
it is built once per call by AgentSession and passed on every invoke/stream.
Live objects live here, never in GraphState.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import AgentConfig


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentRuntime:
    session_id: str
    config: AgentConfig
    tracer: Any  # ConversationTracer
    # The one tool gateway (agent/tooling).
    tools: Any
    # Barge-in: set from the transport thread, checked between LLM tokens.
    cancel: threading.Event
    # Testable time (ETA, flap windows).
    clock: Callable[[], datetime] = field(default=_utc_now)
    # Temporary (M2 steps 1-6): the engine the flows still take; removed in step 7.
    engine: Any = None


def build_runtime(engine: Any) -> AgentRuntime:
    """The runtime for one call around its engine."""
    return AgentRuntime(
        session_id=engine.session_id,
        config=engine.config,
        tracer=engine.tracer,
        tools=engine.tools,
        cancel=engine._cancel_requested,
        engine=engine,
    )
