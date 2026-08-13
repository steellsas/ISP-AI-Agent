"""
AgentSession — stable, framework-free entry point for one conversation.

`handle_turn(text) -> reply` is the single seam that every transport (CLI,
Streamlit, voice/FastRTC, telephony) calls. Callers never touch the agent
loop, tool plumbing or message history directly, so those internals — history
management, model swap, prompt changes — can evolve *behind* this boundary
without breaking any caller. This is the "lock the interface first" step:
later work (e.g. memory management) plugs in inside, not on top.

Design: composition over rewrite. AgentSession owns a ReactAgent (the engine)
and exposes a small, intentional surface. The engine keeps working exactly as
before; this only adds a clean boundary in front of it.

Usage:
    session = AgentSession(caller_phone="+37060012345", language="lt")
    print(session.greeting())            # opening line, no user input yet
    print(session.handle_turn("Labas"))  # one utterance in -> one reply out
"""

from __future__ import annotations

import os
from typing import Any

from .config import AgentConfig
from .graph import build_turn_graph
from .react_agent import ReactAgent
from .state import AgentState


class AgentSession:
    """One customer support conversation behind a stable turn interface."""

    def __init__(
        self,
        caller_phone: str = "unknown",
        language: str = "lt",
        config: AgentConfig | None = None,
        tracer=None,
        engine: str | None = None,
    ):
        """
        Start a session.

        Args:
            caller_phone: Customer's phone number.
            language: Language code ("lt" or "en").
            config: Optional agent configuration (defaults applied if None).
            tracer: Optional ConversationTracer (defaults to the JSONL sink).
            engine: orchestration engine — "graph" (LangGraph, default) or
                "legacy" (direct ReactAgent loop, rollback). Overridable by the
                AGENT_ENGINE env var. Behaviour is identical in step 3.1.
        """
        self._agent = ReactAgent(
            caller_phone=caller_phone,
            language=language,
            config=config,
            tracer=tracer,
        )

        # Orchestration engine (docs/ROADMAP_REFACTORING.md): "v2" is the
        # DEFAULT since 2026-08-13 — the refactored graph_v2 engine (typed
        # GraphState, SqliteSaver checkpoints, diagnosis subgraph, one node per
        # file). "graph" = the pre-refactor LangGraph wrapper, "legacy" = the
        # direct ReactAgent loop; both kept as rollback via AGENT_ENGINE.
        mode = engine or os.getenv("AGENT_ENGINE", "v2")
        self._engine_mode = mode
        self._use_graph = mode != "legacy"
        if mode == "v2":
            from .graph_v2 import build_graph as build_v2_graph

            self._graph = build_v2_graph(self._agent)
        elif self._use_graph:
            self._graph = build_turn_graph(self._agent)
        else:
            self._graph = None
        self._graph_config = {"configurable": {"thread_id": self._agent.session_id}}

    def _graph_input(self, text: str | None) -> dict:
        """Shape one turn's input for the active graph engine."""
        if self._engine_mode == "v2":
            from .graph_v2 import TurnScratch

            # Seeding caller_phone keeps the checkpointed GraphState complete
            # from the very first turn; TurnScratch reset == begin_turn().
            return {
                "caller_phone": self._agent.state.caller_phone,
                "turn": TurnScratch(user_input=text),
            }
        return {"user_input": text}

    def _graph_reply(self, out: dict) -> str | None:
        """Read the reply from the graph's output state."""
        if self._engine_mode == "v2":
            turn = out.get("turn")
            return turn.reply if turn is not None else None
        return out.get("reply")

    def end_session(self, outcome: str | None = None) -> None:
        """Mark the conversation finished (emits session_end to the trace).

        Idempotent. Transports call this when the call ends (CLI quit, voice
        hang-up) so every conversation's trace is properly closed.
        """
        self._agent.end_session(outcome=outcome)

    @property
    def session_id(self) -> str:
        """The conversation's trace id (also the JSONL filename stem)."""
        return self._agent.session_id

    @property
    def tracer(self):
        """The ConversationTracer for this call (lets the voice pipeline log)."""
        return self._agent.tracer

    def greeting(self) -> str:
        """
        Return the conversation's opening message.

        The first turn has no user input — the agent greets, then waits for the
        customer's problem. Voice/telephony speak this before listening.
        """
        if self._use_graph:
            return self._graph_reply(
                self._graph.invoke(self._graph_input(None), self._graph_config)
            )
        return self._agent.run_until_response()

    def handle_turn(self, text: str) -> str:
        """
        Process one customer utterance and return the agent's reply.

        This is THE interface. It runs the full internal tool loop (the model
        may call several tools) and returns only the customer-facing text.

        Args:
            text: The customer's message for this turn.

        Returns:
            The agent's reply string.
        """
        if self._use_graph:
            return self._graph_reply(
                self._graph.invoke(self._graph_input(text), self._graph_config)
            )
        return self._agent.run_until_response(text)

    def handle_turn_stream(self, text: str):
        """Streaming variant of handle_turn (Pillar C3): a generator yielding the
        reply's text tokens as the LLM produces them, so the voice pipeline can
        synthesize per sentence and start speaking sooner.

        LangGraph stays the orchestrator — the graph nodes stream their tokens via
        the stream writer and `graph.stream(stream_mode="custom")` surfaces them.
        Falls back to a single chunk (the full reply) when the graph is disabled.
        """
        if not self._use_graph:
            yield self._agent.run_until_response(text)
            return
        if self._engine_mode == "v2":
            # The diagnosis stage is a SUBGRAPH in v2 — custom writer events only
            # surface with subgraphs=True, which wraps every chunk in a
            # (namespace, chunk) pair; unwrap so transports keep receiving raw
            # tokens exactly like the legacy graph emitted them.
            for _ns, chunk in self._graph.stream(
                self._graph_input(text), self._graph_config, stream_mode="custom", subgraphs=True
            ):
                yield chunk
            return
        yield from self._graph.stream(
            self._graph_input(text), self._graph_config, stream_mode="custom"
        )

    def request_cancel(self) -> None:
        """Barge-in (Phase 5 PR3): stop the running streaming turn — the engine's
        token loop closes the LLM stream and re-asks the interrupted question.
        Thread-safe; no-op when no turn is running."""
        self._agent.request_cancel()

    # --- Read-only views for transports / debug UIs ------------------------
    # Exposed as properties (not the agent itself) so callers depend on this
    # surface, not on ReactAgent internals.

    @property
    def is_complete(self) -> bool:
        """Whether the conversation has ended."""
        return self._agent.state.is_complete

    @property
    def state(self) -> AgentState:
        """Current conversation state (customer info, history, flags)."""
        return self._agent.state

    @property
    def config(self) -> AgentConfig:
        """The agent configuration in use (model, language, messages...)."""
        return self._agent.config

    @property
    def stats(self) -> dict[str, Any]:
        """Accumulated LLM statistics for this conversation."""
        return self._agent.get_stats()
