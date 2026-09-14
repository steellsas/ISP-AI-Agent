"""
AgentSession — stable, framework-free entry point for one conversation.

`handle_turn(text) -> reply` is the single seam that every transport (API,
voice, eval) calls. Callers never touch the agent
loop, tool plumbing or message history directly, so those internals — history
management, model swap, prompt changes — can evolve *behind* this boundary
without breaking any caller. This is the "lock the interface first" step:
later work (e.g. memory management) plugs in inside, not on top.

Design: AgentSession owns the LangGraph v2 graph and the ReactAgent engine the
graph nodes call into, and exposes a small, intentional surface.

Usage:
    session = AgentSession(caller_phone="+37060012345", language="lt")
    print(session.greeting())            # opening line, no user input yet
    print(session.handle_turn("Labas"))  # one utterance in -> one reply out
"""

from __future__ import annotations

import threading
from typing import Any

from .config import AgentConfig
from .graph_v2 import GraphState, TurnScratch, build_graph
from .react_agent import ReactAgent
from .runtime import build_runtime


class AgentSession:
    """One customer support conversation behind a stable turn interface."""

    def __init__(
        self,
        caller_phone: str = "unknown",
        language: str = "lt",
        config: AgentConfig | None = None,
        tracer=None,
        checkpointer=None,
        thread_id: str | None = None,
    ):
        """
        Start a session.

        Args:
            caller_phone: Customer's phone number.
            language: Language code ("lt" or "en").
            config: Optional agent configuration (defaults applied if None).
            tracer: Optional ConversationTracer (defaults to the JSONL sink).
            checkpointer: The process-wide checkpoint saver (the API service's
                SqliteSaver); None keeps the call state in memory.
            thread_id: Continue an existing call from the checkpointer (defaults
                to this session's own id — a new call).
        """
        self._agent = ReactAgent(
            caller_phone=caller_phone,
            language=language,
            config=config,
            tracer=tracer,
        )

        # LangGraph v2: typed GraphState, SqliteSaver checkpoints, diagnosis
        # subgraph, one node per file.
        self._runtime = build_runtime(self._agent)
        self._graph = build_graph(checkpointer)
        self._graph_config = {"configurable": {"thread_id": thread_id or self._agent.session_id}}
        # Results of background work (analyst, speculation, telemetry refresh),
        # handed to the NEXT turn through its graph input — no thread writes state.
        self._inbox: dict[str, Any] = {}
        self._inbox_lock = threading.Lock()

    def _graph_input(self, text: str | None) -> dict:
        """Shape one turn's graph input: a fresh turn scratch. The rest of the state
        comes from the checkpoint — on the very first invoke it is seeded from the
        engine's initial state (caller phone, config-derived limits)."""
        with self._inbox_lock:
            inbox, self._inbox = self._inbox, {}
        turn = TurnScratch(
            user_input=text,
            injected_reply=inbox.get("injected_reply"),
            bg_diagnosis=inbox.get("bg_diagnosis"),
        )
        values = self._graph.get_state(self._graph_config).values
        update: dict[str, Any] = {}
        if not values:
            initial = self._agent.state
            update = {name: getattr(initial, name) for name in type(initial).model_fields}
        if inbox.get("analyst_notes"):
            voice = values["voice"] if values else self._agent.state.voice
            update["voice"] = voice.model_copy(update={"analyst_notes": inbox["analyst_notes"]})
        update["turn"] = turn
        return update

    def _current_state(self) -> GraphState:
        """The call state as checkpointed after the last turn (the engine's initial
        state before the first one)."""
        values = self._graph.get_state(self._graph_config).values
        return GraphState(**values) if values else self._agent.state

    def _write_between_turns(self, write) -> None:
        """Run an engine write outside a turn: on a copy of the checkpointed state,
        stored back with graph.update_state (before the first turn the engine's
        initial state is edited and seeds the first invoke)."""
        if not self._graph.get_state(self._graph_config).values:
            write()
            return
        self._agent.state = self._current_state().model_copy(deep=True)
        write()
        state = self._agent.state
        self._graph.update_state(
            self._graph_config,
            {name: getattr(state, name) for name in type(state).model_fields if name != "turn"},
        )

    @staticmethod
    def _graph_reply(out: dict) -> str | None:
        """Read the reply from the graph's output state."""
        turn = out.get("turn")
        return turn.reply if turn is not None else None

    def end_session(self, outcome: str | None = None) -> None:
        """Mark the conversation finished (emits session_end to the trace).

        Idempotent. Transports call this when the call ends (voice hang-up, API
        delete, eval) so every conversation's trace is properly closed. The
        hang-up net and the call record run on the checkpointed state.
        """
        self._write_between_turns(lambda: self._agent.end_session(outcome=outcome))

    @property
    def session_id(self) -> str:
        """The conversation's trace id (also the JSONL filename stem)."""
        return self._agent.session_id

    @property
    def tracer(self):
        """The ConversationTracer for this call (lets the voice pipeline log)."""
        return self._agent.tracer

    def asr_context(self) -> str | None:
        """Per-turn STT biasing context (VOICE_PLAN V1): the agent's LAST
        question + the expected answer vocabulary of the pending evidence fact.
        Whisper biases decoding toward prompt vocabulary, so short/garbled
        answers ("nedaga") decode toward what the conversation expects
        ("nedega"). Best-effort — None on any hiccup, the ASR then uses only
        its static domain prompt."""
        try:
            a = self._agent
            parts: list[str] = []
            q = (a.state.dialog.last_question or "").strip()
            if q:
                parts.append(f"Klausimas: {q}")
            words: list[str] = []
            pending = a.state.diagnosis.pending_evidence_key
            r = a.state.resolution.procedure or {}
            if pending and r.get("verdict"):
                from .evidence import _PENDING_ANSWERS, spec_for

                spec = spec_for(r.get("verdict"))
                item = (spec.get("client") or {}).get(pending) if spec else None
                for marks in ((item or {}).get("atsakymai") or {}).values():
                    words += [str(m) for m in marks]
                if not words:  # built-in vocabulary for the piloted keys
                    for _value, marks in _PENDING_ANSWERS.get(pending, []):
                        words += [str(m) for m in marks]
            if words:
                parts.append("Galimi atsakymai: " + ", ".join(dict.fromkeys(words)) + ".")
            return (" ".join(parts)[:400]) or None
        except Exception:  # pragma: no cover - biasing must never break a turn
            return None

    def apply_overlay(self, texts: list[str]) -> None:
        """Duplex-hearing 2: hand the caller's over-the-voice words to the
        engine (deterministic ingest + one-shot narrator note)."""
        self._write_between_turns(lambda: self._agent.apply_overlay(texts))

    def apply_delivery(self, sentences: list[str], delivered: int) -> None:
        """D1: after a barge-in, keep in history only the sentences the caller
        actually heard; the unheard tail resurfaces via the narrator next turn."""
        self._write_between_turns(lambda: self._agent.apply_delivery(sentences, delivered))

    def endpoint_hint(self, partial_text: str) -> tuple[str, int | None]:
        """E2 duplex: how much trailing silence the utterance-so-far deserves —
        ("slow", ms) mid-thought, ("fast", ms) when it already IS the expected
        answer, ("normal", None) otherwise. Best-effort, deterministic."""
        try:
            from .endpoint import classify_endpoint

            return classify_endpoint(self._agent, partial_text)
        except Exception:  # pragma: no cover - a hint must never break a turn
            return ("normal", None)

    def analyst_next(self) -> None:
        """W2: the quiet analyst's background read — advisory notes for the
        narrator's next turn (never facts, never routing)."""
        from .analyst import run_analyst

        notes = run_analyst(self._agent)
        if notes:
            with self._inbox_lock:
                self._inbox["analyst_notes"] = notes

    def speculate_next(self, synthesize=None) -> None:
        """S1: prepare the branch cache for the OPEN question (background
        thread entry — pure planning + standalone LLM/TTS, no state writes)."""
        from .speculation import precompute

        precompute(self._agent, synthesize)

    def speculation_match(self, transcript: str) -> bytes | None:
        """S1 serve gate: when the utterance maps to a prepared branch, arm the
        injection (the engine's turn then skips the LLM) and return the cached
        audio; None on any doubt — the normal path runs untouched."""
        from .speculation import match

        branch = match(self._agent, transcript)
        if not branch:
            return None
        with self._inbox_lock:
            self._inbox["injected_reply"] = {
                "kind": branch["kind"],
                "key": branch.get("key"),
                "text": branch["text"],
            }
        self._last_injected_text = branch["text"]
        return branch.get("audio") or None

    def speculate_background_diagnosis(self) -> None:
        """S2: a READ-ONLY telemetry refresh while the caller is busy — the
        result is folded in at the next turn's start (never mid-turn)."""
        try:
            engine = self._agent
            cid = engine.state.identity.customer_id
            if not cid or engine.state.closing.case_closed:
                return
            from .tooling import telemetry

            result = telemetry(engine, mode="recheck", reason="background_refresh")
        except Exception:  # pragma: no cover - background best-effort
            return
        with self._inbox_lock:
            self._inbox["bg_diagnosis"] = result.observation

    def is_pending_answer(self, text: str) -> bool:
        """Does `text` answer the evidence question that is currently out? (The
        deterministic reader — used to tell a caller's answer from an echo.)"""
        s = self._agent.state
        key = s.diagnosis.pending_evidence_key
        if not key:
            return False
        from .evidence import read_pending_answer, spec_for

        spec = spec_for((s.resolution.procedure or {}).get("verdict")) or {}
        item = (spec.get("client") or {}).get(key)
        return read_pending_answer(str(key), text, item) is not None

    def awaiting_caller(self) -> bool:
        """True while the call is open and a question/instruction is standing —
        the gate for the silence check-in (G3): 'Kaip sekasi?' only makes sense
        when the caller was asked to DO or ANSWER something."""
        try:
            a = self._agent
            return not a.state.closing.case_closed and bool(
                (a.state.dialog.last_question or "").strip()
            )
        except Exception:  # pragma: no cover
            return False

    def last_spoken_text(self) -> str:
        """The agent's most recent spoken reply (echo reference for L3a) —
        falls back to the standing question when no reply is recorded yet."""
        try:
            for m in reversed(self._agent.state.messages):
                if m.get("role") == "assistant" and (m.get("content") or "").strip():
                    return str(m["content"])
            return self._agent.state.dialog.last_question or ""
        except Exception:  # pragma: no cover
            return ""

    def anchor_text(self) -> str:
        """The exact question to re-say after a swallowed backchannel turn."""
        try:
            return self._agent.anchor_text()
        except Exception:  # pragma: no cover
            return ""

    def greeting(self) -> str:
        """
        Return the conversation's opening message.

        The first turn has no user input — the agent greets, then waits for the
        customer's problem. Voice/telephony speak this before listening.
        """
        return self._graph_reply(
            self._graph.invoke(self._graph_input(None), self._graph_config, context=self._runtime)
        )

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
        return self._graph_reply(
            self._graph.invoke(self._graph_input(text), self._graph_config, context=self._runtime)
        )

    def handle_turn_stream(self, text: str):
        """Streaming variant of handle_turn (Pillar C3): a generator yielding the
        reply's text tokens as the LLM produces them, so the voice pipeline can
        synthesize per sentence and start speaking sooner.

        LangGraph stays the orchestrator — the graph nodes stream their tokens via
        the stream writer and `graph.stream(stream_mode="custom")` surfaces them.
        """
        # The diagnosis stage is a SUBGRAPH — custom writer events only surface
        # with subgraphs=True, which wraps every chunk in a (namespace, chunk)
        # pair; unwrap so transports receive raw tokens.
        for _ns, chunk in self._graph.stream(
            self._graph_input(text),
            self._graph_config,
            context=self._runtime,
            stream_mode="custom",
            subgraphs=True,
        ):
            yield chunk

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
        return self._agent.state.closing.is_complete

    @property
    def state(self) -> GraphState:
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
