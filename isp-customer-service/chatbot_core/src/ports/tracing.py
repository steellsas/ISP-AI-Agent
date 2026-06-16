"""ConversationTracer port — structured per-conversation trace.

A thin seam at the single AgentSession boundary, so the SAME trace is produced
regardless of transport (CLI / voice / future UI). Implementations decide the
sink (a JSONL file now; a log aggregator or live UI feed later) without any
change to the core. See chatbot_core/docs/stebejimo_dizainas.md.

Interface only — no behaviour. Implementations stamp session_id, timestamp and
schema version; callers pass only the event type and its fields.
"""

from __future__ import annotations

from typing import Any, Protocol


class ConversationTracer(Protocol):
    """Emit one structured event into a conversation's trace.

    Contract:
    - Best-effort: emit MUST NOT raise into the conversation flow (a broken
      sink can never break a call).
    - Cheap / non-blocking: it runs on the conversation's hot path (incl.
      voice), so it must not add latency.
    - The implementation stamps `session_id`, `ts` and schema `v`; the caller
      passes the event `type` and any extra fields.
    """

    def emit(self, event_type: str, **fields: Any) -> None:
        """Record one event (e.g. emit("tool_call", name=..., args=...))."""
        ...
