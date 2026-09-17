"""
AgentRuntime — the per-call dependencies every graph node and flow receives (D-01).

LangGraph hands it to nodes as `runtime.context` (StateGraph context_schema);
AgentSession builds it once per call with new_call() and passes it on every
invoke/stream. Live objects live here, never in GraphState.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import AgentConfig, create_config


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class LLMStats:
    """Accumulated LLM statistics for a conversation."""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    cached_calls: int = 0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def average_latency_ms(self) -> float:
        non_cached = self.total_calls - self.cached_calls
        if non_cached > 0:
            return self.total_latency_ms / non_cached
        return 0.0

    def add_call(
        self,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: float,
        cached: bool,
        model: str,
    ):
        """Add stats from one LLM call."""
        self.total_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.total_latency_ms += latency_ms
        if cached:
            self.cached_calls += 1
        self.model = model

    def to_dict(self) -> dict:
        """Convert to dictionary for UI."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_cost": self.total_cost,
            "average_latency_ms": self.average_latency_ms,
            "cached_calls": self.cached_calls,
            "model": self.model,
        }


@dataclass(frozen=True)
class AgentRuntime:
    session_id: str
    config: AgentConfig
    tracer: Any  # ConversationTracer
    # The one tool gateway (agent/tooling).
    tools: Any
    # Barge-in: set from the transport thread, checked between LLM tokens.
    cancel: threading.Event = field(default_factory=threading.Event)
    # Set once the call's session_end ran (end_session is idempotent).
    ended: threading.Event = field(default_factory=threading.Event)
    llm_stats: LLMStats = field(default_factory=LLMStats)
    # Testable time (ETA, flap windows).
    clock: Callable[[], datetime] = field(default=_utc_now)
    # When the call started (the contact record's duration).
    started_at: datetime = field(default_factory=_utc_now)


def new_call(
    caller_phone: str = "unknown",
    language: str = "lt",
    config: AgentConfig | None = None,
    tracer: Any = None,
    tools: Any = None,
) -> tuple[Any, AgentRuntime]:
    """The initial state and the runtime for one new call (opens its trace)."""
    from src.adapters.tracing import get_tracer, new_session_id

    from .graph_v2.state import DialogState, GraphState, IdentityState
    from .tooling import LocalToolProvider, ToolGateway

    config = config or create_config(language=language)
    session_id = new_session_id()
    tracer = tracer if tracer is not None else get_tracer(session_id)
    tracer.emit(
        "session_start", caller_phone=caller_phone, language=config.language, model=config.model
    )
    state = GraphState(
        identity=IdentityState(caller_phone=caller_phone),
        dialog=DialogState(max_turns=config.max_turns),
    )
    runtime = AgentRuntime(
        session_id=session_id,
        config=config,
        tracer=tracer,
        tools=tools if tools is not None else ToolGateway(LocalToolProvider()),
    )
    return state, runtime
