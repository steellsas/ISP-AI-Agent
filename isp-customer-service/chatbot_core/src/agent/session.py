"""
AgentSession — stable, framework-free entry point for one conversation.

`handle_turn(text) -> reply` is the single seam that every transport (API,
voice, eval) calls. Callers never touch the agent
loop, tool plumbing or message history directly, so those internals — history
management, model swap, prompt changes — can evolve *behind* this boundary
without breaking any caller. This is the "lock the interface first" step:
later work (e.g. memory management) plugs in inside, not on top.

Design: AgentSession owns the call's LangGraph graph and its AgentRuntime and
exposes a small, intentional surface. The call state lives in the checkpoint;
the session keeps the last committed snapshot for read-only views.

Usage:
    session = AgentSession(caller_phone="+37060012345", language="lt")
    print(session.greeting())            # opening line, no user input yet
    print(session.handle_turn("Labas"))  # one utterance in -> one reply out
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from .call_record.finalizer import finalize
from .config import AgentConfig
from .delivery import apply_delivery, apply_overlay
from .graph_v2 import GraphState, TurnScratch, build_graph
from .runtime import new_call

logger = logging.getLogger(__name__)


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
        # The initial state seeds the first invoke; afterwards the checkpoint
        # holds the call and _state is the last committed snapshot.
        self._state, self._runtime = new_call(caller_phone, language, config, tracer)
        self._graph = build_graph(checkpointer)
        self._graph_config = {"configurable": {"thread_id": thread_id or self._runtime.session_id}}
        if thread_id:
            self._refresh_state()
        # Results of background work (the analyst, the telemetry refresh),
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
            bg_diagnosis=inbox.get("bg_diagnosis"),
        )
        values = self._graph.get_state(self._graph_config).values
        update: dict[str, Any] = {}
        if not values:
            initial = self._state
            update = {name: getattr(initial, name) for name in type(initial).model_fields}
        if inbox.get("analyst_signals"):
            voice = values["voice"] if values else self._state.voice
            update["voice"] = voice.model_copy(update={"analyst_signals": inbox["analyst_signals"]})
        update["turn"] = turn
        return update

    def _current_state(self) -> GraphState:
        """The call state as checkpointed after the last turn (the initial state
        before the first one)."""
        values = self._graph.get_state(self._graph_config).values
        return GraphState(**values) if values else self._state

    def _refresh_state(self) -> None:
        self._state = self._current_state()

    def _emit_turn_plan(self) -> None:
        """One `turn_plan` trace event per turn — the plan the turn ran."""
        from .decide.plan import Say, TurnPlan

        plan = self._state.turn.plan
        if plan is None:  # a cancelled or failed turn
            owner = "diagnosis" if self._state.identity.customer_id else "identification"
            plan = TurnPlan(owner=owner, rule="dialog.no_reply", say=Say(kind="none")).model_dump(
                mode="json"
            )
        self._runtime.tracer.emit("turn_plan", **plan)

    def _write_between_turns(self, write) -> None:
        """Run a write outside a turn — `write(state, rt)` on a copy of the
        checkpointed state, stored back with graph.update_state (before the first
        turn the initial state is edited and seeds the first invoke)."""
        if not self._graph.get_state(self._graph_config).values:
            write(self._state, self._runtime)
            return
        state = self._current_state().model_copy(deep=True)
        write(state, self._runtime)
        self._graph.update_state(
            self._graph_config,
            {name: getattr(state, name) for name in type(state).model_fields if name != "turn"},
        )
        self._state = state

    @staticmethod
    def _graph_reply(out: dict) -> str | None:
        """Read the reply from the graph's output state."""
        turn = out.get("turn")
        return turn.reply if turn is not None else None

    def end_session(self, transport_end: str | None = None) -> None:
        """Mark the conversation finished (emits session_end to the trace).

        Idempotent. Transports call this when the call ends (voice hang-up, API
        delete, eval) so every conversation's trace is properly closed. The
        hang-up net and the call record run on the checkpointed state.
        """
        self._write_between_turns(
            lambda state, rt: finalize(state, rt, transport_end=transport_end)
        )

    @property
    def session_id(self) -> str:
        """The conversation's trace id (also the JSONL filename stem)."""
        return self._runtime.session_id

    @property
    def tracer(self):
        """The ConversationTracer for this call (lets the voice pipeline log)."""
        return self._runtime.tracer

    def asr_context(self) -> str | None:
        """Per-turn STT biasing context (VOICE_PLAN V1): the agent's LAST
        question + the expected answer vocabulary of the pending evidence fact.
        Whisper biases decoding toward prompt vocabulary, so short/garbled
        answers ("nedaga") decode toward what the conversation expects
        ("nedega"). Best-effort — None on any hiccup, the ASR then uses only
        its static domain prompt."""
        try:
            a = self
            parts: list[str] = []
            q = (a.state.dialog.last_question or "").strip()
            if q:
                parts.append(f"Klausimas: {q}")
            words: list[str] = []
            pending = a.state.diagnosis.pending_evidence_key
            r = a.state.resolution.procedure or {}
            if pending and r.get("verdict"):
                from .contract.locale import vocab_map
                from .evidence import spec_for

                spec = spec_for(r.get("verdict"))
                item = (spec.get("client") or {}).get(pending) if spec else None
                from .contract.locale import vocab

                for name in ((item or {}).get("answers") or {}).values():
                    words += [str(m) for m in vocab(name)]
                if not words:  # built-in vocabulary for the piloted keys
                    for _value, marks in vocab_map("pending_answers").get(pending, []):
                        words += [str(m) for m in marks]
            if words:
                parts.append("Galimi atsakymai: " + ", ".join(dict.fromkeys(words)) + ".")
            return (" ".join(parts)[:400]) or None
        except Exception:  # pragma: no cover - biasing must never break a turn
            return None

    def apply_overlay(self, texts: list[str]) -> None:
        """Duplex-hearing 2: hand the caller's over-the-voice words to the
        engine (deterministic ingest + one-shot narrator note)."""
        self._write_between_turns(lambda state, rt: apply_overlay(state, rt, texts))

    def apply_delivery(self, sentences: list[str], delivered: int) -> None:
        """D1: after a barge-in, keep in history only the sentences the caller
        actually heard; the unheard tail resurfaces via the narrator next turn."""
        self._write_between_turns(lambda state, rt: apply_delivery(state, rt, sentences, delivered))

    def endpoint_hint(self, partial_text: str) -> tuple[str, int | None]:
        """E2 duplex: how much trailing silence the utterance-so-far deserves —
        ("slow", ms) mid-thought, ("fast", ms) when it already IS the expected
        answer, ("normal", None) otherwise. Best-effort, deterministic."""
        try:
            from .endpoint import classify_endpoint

            return classify_endpoint(self._state, self._runtime, partial_text)
        except Exception:  # pragma: no cover - a hint must never break a turn
            return ("normal", None)

    def use_background_analyst(self) -> None:
        """The transport has a background window (voice): the analyst reads there, so no
        turn waits for it."""
        self._write_between_turns(lambda state, rt: setattr(state.voice, "background_reads", True))

    def analyst_next(self) -> None:
        """The analyst's background read (ANALYST_MODE=async, the voice default): its
        signals are applied on this state and the tone ones ride to the next turn."""
        from .analyst.node import apply, mode, read

        if mode(self._state) != "async":
            return
        signals = read(self._state, self._runtime)
        if not signals:
            return
        apply(self._state, self._runtime, signals)
        carried = self._state.voice.analyst_signals
        if carried:
            with self._inbox_lock:
                self._inbox["analyst_signals"] = carried

    def refresh_telemetry_next(self) -> None:
        """A READ-ONLY telemetry refresh while the caller is busy — the result is folded
        in at the next turn's start (never mid-turn)."""
        try:
            state = self._state
            cid = state.identity.customer_id
            if not cid or state.closing.case_closed:
                return
            from .tooling import telemetry

            result = telemetry(state, self._runtime, mode="recheck", reason="background_refresh")
        except Exception:  # pragma: no cover - background best-effort
            return
        with self._inbox_lock:
            self._inbox["bg_diagnosis"] = result.observation

    def is_pending_answer(self, text: str) -> bool:
        """Does `text` answer the evidence question that is currently out? (The
        deterministic reader — used to tell a caller's answer from an echo.)"""
        s = self._state
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
            s = self._state
            return not s.closing.case_closed and bool((s.dialog.last_question or "").strip())
        except Exception:  # pragma: no cover
            return False

    def last_spoken_text(self) -> str:
        """The agent's most recent spoken reply (echo reference for L3a) —
        falls back to the standing question when no reply is recorded yet."""
        try:
            for m in reversed(self._state.messages):
                if m.get("role") == "assistant" and (m.get("content") or "").strip():
                    return str(m["content"])
            return self._state.dialog.last_question or ""
        except Exception:  # pragma: no cover
            return ""

    def anchor_text(self) -> str:
        """The exact question to re-say after a swallowed backchannel turn."""
        from .dialog_utils import anchor_text

        try:
            return anchor_text(self._state, self._runtime)
        except Exception:  # pragma: no cover
            return ""

    def greeting(self) -> str:
        """
        Return the conversation's opening message.

        The first turn has no user input — the agent greets, then waits for the
        customer's problem. Voice/telephony speak this before listening.
        """
        out = self._graph.invoke(self._graph_input(None), self._graph_config, context=self._runtime)
        self._refresh_state()
        self._emit_turn_plan()
        return self._graph_reply(out)

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
        out = self._graph.invoke(self._graph_input(text), self._graph_config, context=self._runtime)
        self._refresh_state()
        self._emit_turn_plan()
        return self._graph_reply(out)

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
        try:
            for _ns, chunk in self._graph.stream(
                self._graph_input(text),
                self._graph_config,
                context=self._runtime,
                stream_mode="custom",
                subgraphs=True,
            ):
                yield chunk
        finally:
            self._refresh_state()
            self._emit_turn_plan()

    def request_cancel(self) -> None:
        """Barge-in (Phase 5 PR3): stop the running streaming turn — the engine's
        token loop closes the LLM stream and re-asks the interrupted question.
        Thread-safe; no-op when no turn is running."""
        self._runtime.cancel.set()

    # --- Read-only views for transports / debug UIs ------------------------
    # Exposed as properties (not the agent itself) so callers depend on this
    # surface, not on engine internals.

    @property
    def is_complete(self) -> bool:
        """Whether the conversation has ended."""
        return self._state.closing.is_complete

    @property
    def state(self) -> GraphState:
        """The call state after the last turn (customer info, history, flags)."""
        return self._state

    @property
    def config(self) -> AgentConfig:
        """The agent configuration in use (model, language, messages...)."""
        return self._runtime.config

    @property
    def stats(self) -> dict[str, Any]:
        """Accumulated LLM statistics for this conversation."""
        return self._runtime.llm_stats.to_dict()
