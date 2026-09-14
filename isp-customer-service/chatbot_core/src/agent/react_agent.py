"""
Agent - ISP Customer Support

Drives the support conversation with native LLM function/tool calling.

Loop (run_turn_scoped_stream, called by the LangGraph v2 nodes):
1. The model receives the conversation + tool schemas (tool_choice="auto").
2. It either calls one or more tools (structured tool_calls) or replies in text.
3. Tool results are fed back as role:"tool" messages and the model continues.
4. When the model replies with text (no tool call), that is the customer answer,
   streamed token by token (see services.llm.stream_tool_completion).

Callers use agent.session.AgentSession; the engine is internal.
"""

import json
import logging
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

# LLM client
from src.services.llm.client import (
    get_last_call_stats,
    stream_tool_completion,
)

from .config import AgentConfig, create_config
from .dialog_utils import is_question, progress_key, similar
from .graph_v2.state import DialogState, GraphState, IdentityState
from .prompts import load_system_prompt
from .tooling import LocalToolProvider, ToolGateway
from .trace import emit_case, tools_called_this_session, trace_note

# Conversation trace (observability). Optional: if the adapter can't import,
# fall back to a no-op so tracing never breaks the agent.
try:
    from src.adapters.tracing import get_tracer, new_session_id

    _TRACING_AVAILABLE = True
except ImportError:  # pragma: no cover - defensive
    _TRACING_AVAILABLE = False

    def new_session_id() -> str:
        return "no-trace"

    def get_tracer(session_id, **_kwargs):
        class _Null:
            def emit(self, *_a, **_k):
                return None

        return _Null()


# Tools
try:
    from .tools import REAL_TOOLS as TOOLS
    from .tools import get_tools_description, get_tools_schema

    USING_REAL_TOOLS = True
except ImportError:
    USING_REAL_TOOLS = False
    TOOLS = []

    def get_tools_description():
        return "No tools available"

    def get_tools_schema():
        return []


logger = logging.getLogger(__name__)

# Closing rules moved to closing_flow.py (R3, docs/ROADMAP_REFACTORING.md §4);
# the alias keeps existing imports/tests working during the migration.

# Verdict glossaries moved to glossary.py (R3); aliases keep call sites working.


# Deterministic backstops (LT), used when the prompt-level nudge fails to break a
# loop. Kept here (not the language service) so the escalation is self-contained.
_STUCK_OFFER_CODE = "Atsiprašau, vis nepavyksta išgirsti. Gal turite abonento kodą nuo sąskaitos?"
_STUCK_REGISTER = (
    "Užregistruosiu jūsų problemą ir mūsų specialistas su jumis susisieks. Geros dienos!"
)


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


class ReactAgent:
    """
    ReAct pattern agent for ISP customer support.

    Attributes:
        state: Current conversation state
        config: Agent configuration
        system_prompt: Formatted system prompt
    """

    def __init__(
        self,
        caller_phone: str = "unknown",
        language: str = "lt",
        config: AgentConfig = None,
        tracer=None,
    ):
        """
        Initialize agent.

        Args:
            caller_phone: Customer's phone number
            language: Language code ("lt" or "en")
            config: Agent configuration (uses default if None)
            tracer: ConversationTracer (defaults to the configured JSONL sink).
        """
        # Create config with language if not provided
        if config is None:
            self.config = create_config(language=language)
        else:
            self.config = config

        self.state = GraphState(
            identity=IdentityState(caller_phone=caller_phone),
            dialog=DialogState(max_turns=self.config.max_turns),
        )

        # Conversation trace: one file per session, identical across transports.
        self.session_id = new_session_id()
        self.tracer = tracer if tracer is not None else get_tracer(self.session_id)
        self._session_ended = False
        self.tracer.emit(
            "session_start",
            caller_phone=caller_phone,
            language=self.config.language,
            model=self.config.model,
        )

        # Initialize LLM stats tracking
        self.llm_stats = LLMStats()
        # Barge-in cancel (Phase 5 PR3): set via request_cancel() from any
        # thread; the streaming token loop checks it BETWEEN TOKENS — the LLM
        # stream closes mid-generation and the cancelled-turn bookkeeping runs
        # (partial reply recorded, interrupted question re-asked). LangGraph
        # runs the node to completion in the background, so an outer
        # generator-close never reaches this loop — the flag is the only
        # reliable cancel path (verified 2026-08-06).
        self._cancel_requested = threading.Event()
        # S1 speculation (2026-08-24): the branch cache prepared while the
        # caller was answering, and the matched reply injected past the LLM.
        self._spec_cache: dict | None = None
        # The one gateway every tool call goes through (gate, trace, state update).
        self.tools = ToolGateway(LocalToolProvider())

        # OpenAI function-calling schemas passed to the LLM on every step.
        # The model picks which tools to call (tool_choice="auto"); this is the
        # single source of truth, derived from the Tool dataclass.
        self.tools_schema = get_tools_schema()

        # Load and format system prompt with language
        self.system_prompt = load_system_prompt(
            tools_description=get_tools_description(),
            caller_phone=caller_phone,
            language=self.config.language,
        )

        logger.info(f"ReactAgent initialized for {caller_phone} [lang={self.config.language}]")
        if USING_REAL_TOOLS:
            logger.info("Using REAL tools")
        else:
            logger.warning("Using MOCK tools")

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

    def _build_messages(
        self,
        user_input: str | None = None,
        node_prompt: str | None = None,
        allowed_tools: frozenset[str] | None = None,
    ) -> list:
        """Delegates to narrator_flow.build_messages (R3 extraction)."""
        from .narrator_flow import build_messages

        return build_messages(self, user_input, node_prompt, allowed_tools)

    # Security-sensitive resolution actions — only exposed on the strategy STEP
    # that permits them (update_mac on bind_mac, create_ticket on escalate). So the
    # model cannot bind a device during a CONFIRM step, before the caller confirms.
    _STRATEGY_ACTION_TOOLS = frozenset({"update_mac", "reset_port", "create_ticket"})
    # Diagnostics the ENGINE owns during a strategy — the model must not call them
    # (observed: it looped check_network_status / run_ping_test instead of talking).
    _STRATEGY_DIAG_TOOLS = frozenset(
        {"diagnose_connection", "check_network_status", "run_ping_test", "check_port_status"}
    )

    def _scoped_tools_schema(self, allowed_tools: frozenset[str] | None = None) -> list:
        """Delegates to narrator_flow.scoped_tools_schema (R3 extraction)."""
        from .narrator_flow import scoped_tools_schema

        return scoped_tools_schema(self, allowed_tools)

    def _prune_history(self, messages: list) -> list:
        """Delegates to narrator_flow.prune_history (R3 extraction)."""
        from .narrator_flow import prune_history

        return prune_history(self, messages)

    def _state_facts_block(self) -> str | None:
        """Delegates to narrator_flow.state_facts_block (R3 extraction)."""
        from .narrator_flow import state_facts_block

        return state_facts_block(self)

    def _fresh_diagnose_reason(self) -> str | None:
        """Delegates to walker_flow.fresh_diagnose_reason (R3 extraction)."""
        from .walker_flow import fresh_diagnose_reason

        return fresh_diagnose_reason(self)

    def ensure_diagnosed(self) -> bool:
        """Delegates to walker_flow.ensure_diagnosed (R3 extraction)."""
        from .walker_flow import ensure_diagnosed

        return ensure_diagnosed(self)

    def ensure_action_done(self) -> bool:
        """Delegates to walker_flow.ensure_action_done (R3 extraction)."""
        from .walker_flow import ensure_action_done

        return ensure_action_done(self)

    def _advance_resolution(self, user_input: str | None) -> None:
        """Delegates to walker_flow.advance_resolution (R3 extraction)."""
        from .walker_flow import advance_resolution

        return advance_resolution(self, user_input)

    # --- Solver (Phase 3.8 step 2): shadow only ------------------------------
    # Runs the reasoning solver ALONGSIDE the walker and logs its decision next to the
    # walker's move, so we can compare on real calls before it ever drives a reply.
    # Gated by SOLVER_SHADOW (default off) — it adds one LLM call per diagnosis turn.

    def _build_solver_context(self, user_input: str | None) -> str:
        """Delegates to solver_flow.build_solver_context (R3 extraction)."""
        from .solver_flow import build_solver_context

        return build_solver_context(self, user_input)

    def _shadow_solve(self, user_input: str | None) -> None:
        """Delegates to solver_flow.shadow_solve (R3 extraction)."""
        from .solver_flow import shadow_solve

        return shadow_solve(self, user_input)

    # --- Solver DRIVES (Phase 3.8 step 5a) -----------------------------------
    # Behind SOLVER_DRIVE (default off), for the piloted directions only, the solver runs
    # the turn: it reads the RAG playbook + dialogue + telemetry, decides the next action,
    # the gate validates + the engine executes safety actions by code, and the reply is the
    # solver's spoken text. The walker stays the default and handles every other direction.
    _SOLVER_DRIVE_VERDICTS = frozenset({"no_mac_observed"})  # pilot: dead-router / bridge
    _DRIVE_MAX_TURNS = 14  # hard bailout — never grind the caller forever

    def _ingest_client_evidence(self, user_input: str | None) -> None:
        """Delegates to perception_flow.ingest_client_evidence (R3 extraction)."""
        from .perception_flow import ingest_client_evidence

        return ingest_client_evidence(self, user_input)

    def solver_drive_turn(self, user_input: str | None) -> str | None:
        """Delegates to solver_flow.solver_drive_turn (R3 extraction)."""
        from .solver_flow import solver_drive_turn

        return solver_drive_turn(self, user_input)

    def _plug_report(self, user_input: str | None) -> bool:
        """Delegates to solver_flow.plug_report (R3 extraction)."""
        from .solver_flow import plug_report

        return plug_report(self, user_input)

    def request_cancel(self) -> None:
        """Ask the running streaming turn to stop (thread-safe event). Checked
        between tokens; a no-op when no turn is running (the event is cleared at
        the next turn's start)."""
        self._cancel_requested.set()

    def anchor_text(self) -> str:
        """Delegates to perception_flow.anchor_text (R3 extraction)."""
        from .perception_flow import anchor_text

        return anchor_text(self)

    def classify_side_topic(self, user_input: str | None) -> bool:
        """Delegates to perception_flow.classify_side_topic (R3 extraction)."""
        from .perception_flow import classify_side_topic

        return classify_side_topic(self, user_input)

    def _on_task_question(self, user_input: str | None) -> bool:
        """Delegates to perception_flow.on_task_question (R3 extraction)."""
        from .perception_flow import on_task_question

        return on_task_question(self, user_input)

    def on_turn_cancelled(self, spoken_text: str) -> None:
        """Barge-in cut the reply mid-generation (Phase 5 PR3): record what the
        caller ACTUALLY heard. The ask-bookkeeping is deliberately NOT rolled
        back (review 2026-08-07): the NEXT turn decides — an early answer
        ("taip, dega raudona!") routes normally, a question goes through
        side_topic with the anchor, and an unclear reply holds -> the question
        re-asks naturally. A blanket re-ask made the agent feel robotic when
        callers interrupted BECAUSE they had already understood."""
        s = self.state
        spoken = (spoken_text or "").strip()
        s.messages.append({"role": "assistant", "content": (spoken + " —") if spoken else "—"})
        # An evidence ask that never fully went out must not escalate the wording.
        key = self.state.diagnosis.pending_evidence_key
        if key and self.state.diagnosis.evidence_ask_counts.get(key, 0) > 0:
            self.state.diagnosis.evidence_ask_counts[key] -= 1
        self.tracer.emit("turn_cancelled", spoken=spoken[:160])

    def apply_overlay(self, texts: list[str]) -> None:
        """Duplex-hearing 2: the caller's words spoken OVER the agent's voice
        (echo already filtered by the transport) — deterministic fact ingest
        through the importance gates + a one-shot narrator note. Overlay may
        FILL facts, never steer routing."""
        from .perception_flow import ingest_overlay

        kept = [t.strip() for t in texts if t and t.strip()][:3]
        if not kept:
            return
        for text in kept:
            ingest_overlay(self, text)
        self.state.voice.overlay_heard = kept
        self.tracer.emit("overlay_applied", texts=[t[:120] for t in kept])

    def apply_delivery(self, sentences: list[str], delivered: int) -> None:
        """D1 delivery ledger (live 2026-08-25: the transcript renders before
        the audio, so a barge-in leaves the engine believing the caller heard
        the WHOLE reply). The transport reports how many sentences actually
        finished playing — the history keeps only that prefix, and the unheard
        tail is surfaced to the narrator next turn. A half-played sentence
        counts as NOT heard (repeating it is the natural repair)."""
        total = len(sentences)
        delivered = max(0, min(int(delivered), total))
        if not total or delivered >= total:
            return
        heard = " ".join(s.strip() for s in sentences[:delivered]).strip()
        tail = " ".join(s.strip() for s in sentences[delivered:]).strip()
        s = self.state
        for msg in reversed(s.messages):
            if msg.get("role") == "assistant":
                msg["content"] = (heard + " —") if heard else "—"
                break
        self.state.voice.undelivered_tail = tail or None
        # Andrius 2026-08-26: the agent must NEVER believe it asked a question
        # the caller could not hear. When the "?" lives only in the unheard
        # tail, the ask never happened: the pending evidence key and its ask
        # counter roll back (the caller's next words are NOT an answer to it),
        # the step's presented counter steps back, and the narrator gets a
        # STRONG re-ask directive instead of the advisory tail note.
        # Closing-stage chatter is exempt (live 2026-08-27): garbled farewells
        # kept cutting the goodbye before its "?" and the re-ask machinery
        # looped "Ar dar kuo padėti?" — a closed case never re-asks.
        if "?" in tail and "?" not in heard and not s.closing.case_closed:
            s.dialog.last_question = None
            # The PENDING evidence key deliberately STAYS (live 2026-08-27:
            # clearing it looped the call — the caller kept interrupting with
            # the ANSWER, which then had no key to land on, so the fact never
            # committed and the same question re-asked forever). Only the ask
            # counter steps back so the wording escalation stays fair; an
            # answer that maps still commits, a true non-answer re-asks anyway.
            key = self.state.diagnosis.pending_evidence_key
            if key and self.state.diagnosis.evidence_ask_counts.get(key, 0) > 0:
                self.state.diagnosis.evidence_ask_counts[key] -= 1
            r = s.resolution.procedure or {}
            pres = r.get("presented") or {}
            step_id = r.get("step")
            if step_id and pres.get(step_id, 0) > 0:
                pres[step_id] -= 1
            self.state.voice.unheard_question = tail
            self.state.voice.undelivered_tail = None  # superseded by the strong directive
        self.tracer.emit(
            "delivery",
            delivered=delivered,
            total=total,
            unheard=tail[:160],
            question_unheard=bool(self.state.voice.unheard_question),
        )

    def _commit_driven_reply(self, user_input: str | None, reply: str) -> str:
        """End-of-turn bookkeeping for an engine/solver-driven reply (mirrors the
        walker path's run_turn_scoped_stream): user_turn trace, dialogue history, shared
        finalisation (case snapshot + agent_reply)."""
        if user_input:
            self.state.dialog.last_heard = user_input.strip()
            self.tracer.emit("user_turn", text=user_input)
            self.state.messages.append({"role": "user", "content": user_input})
        self.state.messages.append({"role": "assistant", "content": reply})
        self._finalize_reply(reply)
        return reply

    # Evidence-drive flow moved to evidence_drive.py (R3, roadmap §4) — thin
    # delegates keep every internal call site and test working unchanged.

    def _evidence_question_open(self) -> str | None:
        """Delegates to evidence_drive.evidence_question_open (R3 extraction)."""
        from .evidence_drive import evidence_question_open

        return evidence_question_open(self)

    def _negation_clarify_reply(self, key: str) -> str | None:
        """Delegates to evidence_drive.negation_clarify_reply (R3 extraction)."""
        from .evidence_drive import negation_clarify_reply

        return negation_clarify_reply(self, key)

    def _evidence_drive(self, user_input: str | None) -> str | None:
        """Delegates to evidence_drive.evidence_drive (R3 extraction)."""
        from .evidence_drive import evidence_drive

        return evidence_drive(self, user_input)

    def _drive(self, user_input: str | None) -> str:
        """Delegates to solver_flow.drive (R3 extraction)."""
        from .solver_flow import drive

        return drive(self, user_input)

    def _refresh_diagnosis(self) -> None:
        """Delegates to solver_flow.refresh_diagnosis (R3 extraction)."""
        from .solver_flow import refresh_diagnosis

        return refresh_diagnosis(self)

    def _drive_propose_fix(self, say: str, user_input: str | None) -> str:
        """Delegates to solver_flow.drive_propose_fix (R3 extraction)."""
        from .solver_flow import drive_propose_fix

        return drive_propose_fix(self, say, user_input)

    def _bridge_fail_step(self) -> str:
        """Delegates to solver_flow.bridge_fail_step (R3 extraction)."""
        from .solver_flow import bridge_fail_step

        return bridge_fail_step(self)

    def _drive_escalate(self, decision) -> str:
        """Delegates to solver_flow.drive_escalate (R3 extraction)."""
        from .solver_flow import drive_escalate

        return drive_escalate(self, decision)

    def _walk_resolution(self, user_input: str | None) -> None:
        """Delegates to walker_flow.walk_resolution (R3 extraction)."""
        from .walker_flow import walk_resolution

        return walk_resolution(self, user_input)

    def _emit_rag_injection(self, doc: str | None, section: int, step_id: str, text: str) -> None:
        """Delegates to narrator_flow.emit_rag_injection (R3 extraction)."""
        from .narrator_flow import emit_rag_injection

        return emit_rag_injection(self, doc, section, step_id, text)

    def _pre_turn_guards(self, user_input: str) -> None:
        """Delegates to perception_flow.pre_turn_guards (R3 extraction)."""
        from .perception_flow import pre_turn_guards

        return pre_turn_guards(self, user_input)

    def _engine_resolve_from_slots(self) -> bool:
        """Delegates to perception_flow.engine_resolve_from_slots (R3 extraction)."""
        from .perception_flow import engine_resolve_from_slots

        return engine_resolve_from_slots(self)

    def _reopen_identification(self, user_input: str) -> None:
        """Delegates to identification_flow.reopen_identification (R3 extraction)."""
        from .identification_flow import reopen_identification

        reopen_identification(self, user_input)

    def _block_uncorroborated_escalate(self, step, strat, label, user_input: str | None) -> bool:
        """Delegates to walker_flow.block_uncorroborated_escalate (R3 extraction)."""
        from .walker_flow import block_uncorroborated_escalate

        return block_uncorroborated_escalate(self, step, strat, label, user_input)

    def _classify_confirm_and_route(self, step, strat, user_input: str | None) -> bool:
        """Delegates to walker_flow.classify_confirm_and_route (R3 extraction)."""
        from .walker_flow import classify_confirm_and_route

        return classify_confirm_and_route(self, step, strat, user_input)

    def _advance_instruct(self, r: dict, step, strat, user_input: str | None = None) -> None:
        """Delegates to walker_flow.advance_instruct (R3 extraction)."""
        from .walker_flow import advance_instruct

        return advance_instruct(self, r, step, strat, user_input)

    def _classify_instruct_and_advance(self, step, strat, user_input: str | None) -> bool:
        """Delegates to walker_flow.classify_instruct_and_advance (R3 extraction)."""
        from .walker_flow import classify_instruct_and_advance

        return classify_instruct_and_advance(self, step, strat, user_input)

    def _detect_confirm(self, step, user_input: str | None):
        """Delegates to walker_flow.detect_confirm (R3 extraction)."""
        from .walker_flow import detect_confirm

        return detect_confirm(self, step, user_input)

    # --- Hypothesis: what we believe is wrong, and why -----------------------
    # The verdict tree decides; these just record the belief so the agent can narrate
    # the arc. Evidence comes from telemetry, never from parsing the caller.

    def _open_hypothesis(self, reason: str | None) -> None:
        """Delegates to walker_flow.open_hypothesis (R3 extraction)."""
        from .walker_flow import open_hypothesis

        return open_hypothesis(self, reason)

    def _note_evidence(self, text: str) -> None:
        """Delegates to walker_flow.note_evidence (R3 extraction)."""
        from .walker_flow import note_evidence

        return note_evidence(self, text)

    def _settle_hypothesis(self, status: str, settled_by: str) -> None:
        """Delegates to walker_flow.settle_hypothesis (R3 extraction)."""
        from .walker_flow import settle_hypothesis

        return settle_hypothesis(self, status, settled_by)

    def _turn_may_advance(self, step) -> bool:
        """Delegates to walker_flow.turn_may_advance (R3 extraction)."""
        from .walker_flow import turn_may_advance

        return turn_may_advance(self, step)

    def _scripted_wait_ack(self) -> str | None:
        """Delegates to walker_flow.scripted_wait_ack (D5)."""
        from .walker_flow import scripted_wait_ack

        return scripted_wait_ack(self)

    def _simulate_router_reboot(self) -> None:
        """DEMO/TEST only (SIMULATE_REBOOT=on): delegates to
        executor_flow.simulate_router_reboot_action (S6)."""
        from .executor_flow import simulate_router_reboot_action

        simulate_router_reboot_action(self)

    def _simulate_bridge_connection(self) -> None:
        """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
        wall cable by making an unbound device appear on the line, so the bridge can
        VERIFY it. Off by default → production never fakes a device (the real one appears
        on its own). Best-effort: a failure just leaves the line unchanged."""
        from .executor_flow import simulate_bridge_connection

        simulate_bridge_connection(self)

    def _advance_see_device(self, r: dict) -> None:
        """Delegates to walker_flow.advance_see_device (R3 extraction)."""
        from .walker_flow import advance_see_device

        return advance_see_device(self, r)

    def _advance_reboot_check(self, r: dict, user_input: str | None) -> None:
        """Delegates to walker_flow.advance_reboot_check (S6 hung router)."""
        from .walker_flow import advance_reboot_check

        return advance_reboot_check(self, r, user_input)

    def _advance_line_check(self, r: dict, user_input: str | None) -> None:
        """Delegates to walker_flow.advance_line_check (NT line faults)."""
        from .walker_flow import advance_line_check

        return advance_line_check(self, r, user_input)

    def _reject_and_rediagnose(self, r: dict) -> bool:
        """Delegates to walker_flow.reject_and_rediagnose (R3 extraction)."""
        from .walker_flow import reject_and_rediagnose

        return reject_and_rediagnose(self, r)

    def _route_to(self, r: dict, target: str) -> None:
        """Delegates to walker_flow.route_to (R3 extraction)."""
        from .walker_flow import route_to

        return route_to(self, r, target)

    def _advance_restored(self, r: dict, user_input: str | None) -> None:
        """Delegates to walker_flow.advance_restored (R3 extraction)."""
        from .walker_flow import advance_restored

        return advance_restored(self, r, user_input)

    def _advance_escalate(self, r: dict, step, user_input: str | None) -> None:
        """Delegates to walker_flow.advance_escalate (R3 extraction)."""
        from .walker_flow import advance_escalate

        return advance_escalate(self, r, step, user_input)

    # Ticket-dialogue flow moved to ticket_flow.py (R3, roadmap §4) — thin
    # delegates keep every internal call site and test working unchanged.

    def _registration_claim_guard(self, content: str) -> str | None:
        """Delegates to ticket_flow.registration_claim_guard (R3 extraction)."""
        from .ticket_flow import registration_claim_guard

        return registration_claim_guard(self, content)

    def _begin_ticket_dialogue(self, step) -> None:
        """Delegates to ticket_flow.begin_ticket_dialogue (R3 extraction)."""
        from .ticket_flow import begin_ticket_dialogue

        begin_ticket_dialogue(self, step)

    def _ticket_need(self) -> str:
        """Delegates to ticket_flow.ticket_need (R3 extraction)."""
        from .ticket_flow import ticket_need

        return ticket_need(self)

    def _wants_to_keep_solving(self, user_input: str | None) -> bool:
        """Delegates to ticket_flow.wants_to_keep_solving (R3 extraction)."""
        from .ticket_flow import wants_to_keep_solving

        return wants_to_keep_solving(self, user_input)

    def _abort_ticket_to_solving(self) -> None:
        """Delegates to ticket_flow.abort_ticket_to_solving (R3 extraction)."""
        from .ticket_flow import abort_ticket_to_solving

        abort_ticket_to_solving(self)

    def _ticket_stage_reply(self) -> str:
        """Delegates to ticket_flow.ticket_stage_reply (R3 extraction)."""
        from .ticket_flow import ticket_stage_reply

        return ticket_stage_reply(self)

    @staticmethod
    def _fmt_phone(nr: str | None) -> str:
        """Delegates to ticket_flow.fmt_phone (R3 extraction)."""
        from .ticket_flow import fmt_phone

        return fmt_phone(nr)

    def _finish_ticket_dialogue(self) -> str:
        """Delegates to ticket_flow.finish_ticket_dialogue (R3 extraction)."""
        from .ticket_flow import finish_ticket_dialogue

        return finish_ticket_dialogue(self)

    def _register_ticket_from_state(self, step_id: str | None) -> None:
        """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
        cause from the hypothesis/verdict, actions from this call's trace — never from
        the model's free text (which once invented an invalid ticket_type). Idempotent:
        an existing ticket is never duplicated. Best-effort: a failure is traced and the
        close still proceeds (the call record keeps the outcome)."""
        from .executor_flow import register_ticket_from_state

        register_ticket_from_state(self, step_id)

    def _goto_step(self, r: dict, next_id: str) -> None:
        """Delegates to walker_flow.goto_step (R3 extraction)."""
        from .walker_flow import goto_step

        return goto_step(self, r, next_id)

    def _maybe_finish(self, user_input: str | None) -> None:
        """Delegates to closing_flow.maybe_finish (R3 extraction)."""
        from .closing_flow import maybe_finish

        maybe_finish(self, user_input)

    def _maybe_close_inform(self, user_input: str | None) -> None:
        """Delegates to closing_flow.maybe_close_inform (R3 extraction)."""
        from .closing_flow import maybe_close_inform

        maybe_close_inform(self, user_input)

    def _mark_step_presented(self) -> None:
        """Delegates to narrator_flow.mark_step_presented (R3 extraction)."""
        from .narrator_flow import mark_step_presented

        return mark_step_presented(self)

    def _augment_resolve_result(self, observation: str) -> str:
        """Delegates to narrator_flow.augment_resolve_result (R3 extraction)."""
        from .narrator_flow import augment_resolve_result

        return augment_resolve_result(self, observation)

    def _result_narration_tail(self) -> str:
        """Delegates to narrator_flow.result_narration_tail (R3 extraction)."""
        from .narrator_flow import result_narration_tail

        return result_narration_tail(self)

    def _augment_tool_result(self, name: str, observation: str) -> str:
        """Delegates to narrator_flow.augment_tool_result (R3 extraction)."""
        from .narrator_flow import augment_tool_result

        return augment_tool_result(self, name, observation)

    def _update_state_from_observation(self, action: str, observation: str):
        """Delegates to narrator_flow.update_state_from_observation (R3 extraction)."""
        from .narrator_flow import update_state_from_observation

        return update_state_from_observation(self, action, observation)

    def _preflight_phone(self) -> None:
        """Look up the caller's number at the START of the call (deterministic).

        Runs once, in code (not via the LLM), so by the customer's first turn the
        phone account — if any — is already known and the agent can offer its
        address for confirmation without a tool round-trip. Stored as an
        UNCONFIRMED candidate (anchor rule), never as a confirmed customer.
        """
        from .identification_flow import preflight_phone

        preflight_phone(self)

    def _prefill_slots_from_text(self, text: str) -> None:
        """Deterministic NLU Track A: extract the address from the caller's turn and
        propose it into the slots BEFORE the LLM runs (docs/pokalbio_variklis.md §4).

        The reading is the high-confidence floor — registry-validated street +
        normalized numbers — so the slots get a reliable source independent of the
        LLM. Proposed as HEARD; resolve_address upgrades a confirmed hit to
        RESOLVED. Best-effort: any failure (DB, import) silently no-ops the turn.
        """
        from .identification_flow import prefill_slots_from_text

        prefill_slots_from_text(self, text)

    def end_session(self, outcome: str | None = None) -> None:
        """Emit session_end once (idempotent). Call when the conversation ends."""
        if self._session_ended:
            return
        self._session_ended = True
        # Hang-up safety net (2026-08-05): the call ended MID-STRATEGY with no
        # ticket — the problem is not solved and nobody would follow up (observed
        # live: registration promised, caller hung up via the UI button, ticket
        # never created). Register from state with the interruption on the
        # record; contacts default to the caller-ID number. After-hours
        # philosophy: a human takes over through the ticket.
        s = self.state
        # F3 (live 2026-09-09): a hang-up ON the homework step means the
        # callback was agreed (or at least offered) — closing with a ticket
        # breaks the agreement (TKT registered over "as perskambinsiu").
        if (
            s.identity.customer_id
            and not s.ticket.ticket_id
            and not s.closing.case_closed
            and str((s.resolution.procedure or {}).get("step") or "").endswith("_homework")
        ):
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            self.tracer.emit("decision", intent="hangup_net", action="callback_close")
        if (
            s.identity.customer_id
            and not s.ticket.ticket_id
            and not s.closing.case_closed
            and s.resolution.procedure is not None
        ):
            from .resolution import get_strategy

            # The line's CURRENT truth decides (2026-08-06): a caller who hung up
            # right after "veikia!" must NOT get a technician ticket (observed
            # live: TKT00D19E54 for a healthy line). A recorded fix or one fresh
            # diagnose read showing healthy skips the net; telemetry unreachable
            # -> register anyway (a spare ticket beats an abandoned caller).
            solved = bool(s.resolution.procedure.get("telemetry_fixed"))
            if not solved:
                try:
                    d = self.tools.run(
                        self,
                        "diagnose_connection",
                        {"customer_id": s.identity.customer_id},
                        reason="hangup_net",
                        apply=False,
                    ).data
                    solved = ((d.get("verdict") or {}).get("reason") or "healthy_to_router") == (
                        "healthy_to_router"
                    )
                except Exception:  # pragma: no cover - defensive
                    solved = False
            if solved:
                s.closing.case_closed = True
                s.closing.closed_reason = "resolved"
                self.tracer.emit("decision", intent="hangup_net", action="skip_solved")
            else:
                s.resolution.procedure.setdefault(
                    "escalate_reason", "Pokalbis nutrūko — klientas padėjo ragelį."
                )
                if not s.ticket.contact_phone:
                    s.ticket.contact_phone = s.identity.caller_phone
                if not s.ticket.contact_hours:
                    s.ticket.contact_hours = "bet kada"
                strat = get_strategy(s.resolution.procedure.get("verdict"))
                esc = strat.step("escalate") if strat else None
                self._register_ticket_from_state(esc.id if esc is not None else None)
                if s.ticket.ticket_id:
                    s.closing.closed_reason = "registered"
                    self.tracer.emit("decision", intent="hangup_net", action="register")
        # Structured OUTCOME of the call, built DETERMINISTICALLY from state (Phase 3.10):
        # why they called, the cause + side, what ran, resolved?/ticket, who called. Emitted
        # for the record/reports; DB persistence to the conversations table is a follow-up.
        summary = self._build_call_summary()
        self.tracer.emit("call_summary", **summary)
        self.tracer.emit(
            "session_end",
            outcome=outcome or summary.get("outcome"),
            customer_id=self.state.identity.customer_id,
            ticket_id=self.state.ticket.ticket_id,
            turn_count=self.state.dialog.turn_count,
            llm_calls=self.llm_stats.total_calls,
            total_tokens=self.llm_stats.total_tokens,
            total_cost=round(self.llm_stats.total_cost, 5),
        )
        # Persist the call record to the conversations table (Phase 3.10 slice 1b).
        # Best-effort at the seam: a DB failure must never break call teardown.
        self._persist_call_record(summary, outcome)
        # Write a human-readable transcript next to the JSONL, if supported.
        export = getattr(self.tracer, "export_txt", None)
        if callable(export):
            export()

    def _persist_call_record(self, summary: dict, outcome: str | None) -> None:
        """Write one row to the conversations table: the structured summary + the
        transcript, keyed by session. Sourced entirely from state; never raises."""
        session_id = getattr(self.tracer, "session_id", None)
        if not session_id:
            return  # NullTracer / no session id -> nothing to key the record on
        try:
            from .tools import save_call_record

            save_call_record(
                session_id,
                customer_id=self.state.identity.customer_id,
                messages=self.state.messages,
                outcome=outcome or summary.get("outcome"),
                summary=summary,
                ticket_id=self.state.ticket.ticket_id,
            )
        except Exception as e:  # pragma: no cover - defensive
            trace_note(self.tracer, self.state, "persist_call_record", f"failed: {e}", level="warn")

    def _build_call_summary(self) -> dict:
        """The call's outcome, derived from state — the single source for the record and
        (later) the ticket. No LLM, no new reasoning: it only reports what the engine knows.
        `actions` come from the tool_calls in this session's trace."""
        s = self.state
        net = s.diagnosis.verdicts.get("network") or {}
        h = s.diagnosis.hypothesis or {}
        cause = h.get("cause") or (s.resolution.procedure or {}).get("verdict") or net.get("reason")
        return {
            "purpose": s.intake.problem_type,
            "customer_id": s.identity.customer_id,
            "address": s.identity.customer_address,
            "caller_name": s.identity.caller_name,
            "caller_relation": s.identity.caller_relation,
            "anamnesis": (
                {
                    "raw": s.intake.anamnesis_raw,
                    "when": s.intake.anamnesis_when,
                    "trigger": s.intake.anamnesis_trigger,
                }
                if s.intake.anamnesis_raw
                else None
            ),
            "cause": cause,
            "side": net.get("side"),  # provider | customer | unclear
            "outcome": s.closing.closed_reason,  # resolved | outage | declined | escalated | None
            "resolved": s.closing.closed_reason == "resolved",
            "ticket_id": s.ticket.ticket_id,
            "actions": tools_called_this_session(self.tracer),
            # F4 (Andrius 2026-08-20): a call that ended WITHOUT identification
            # records everything that was heard — the address may have changed
            # its name, the caller may not be the holder; a person reading the
            # record (or the caller phoning back) can pick the thread up.
            "identifikacija_nepavyko": (
                {
                    "girdeta": list(s.intake.heard_utterances)[-6:],
                    "gatve": s.identity.profile.street.value,
                    "namas": s.identity.profile.house.value,
                    "miestas": s.identity.profile.city.value,
                }
                if not s.identity.customer_id and s.intake.problem_type
                else None
            ),
        }

    def _execute_tool_calls(self, message: Any) -> list[dict]:
        """Echo the assistant tool-call message, run each tool through the gate,
        append results to history, trace, and update state. Returns the executed
        list. Shared by step() (non-streaming) and the streaming loop."""
        from .executor_flow import execute_tool_calls

        return execute_tool_calls(self, message)

    def _record_llm_stats(self) -> None:
        """Fold the last LLM call's stats into the running totals + trace."""
        s = get_last_call_stats()
        self.llm_stats.add_call(
            input_tokens=s.get("input_tokens", 0),
            output_tokens=s.get("output_tokens", 0),
            cost=s.get("cost", 0),
            latency_ms=s.get("latency_ms", 0),
            cached=s.get("cached", False),
            model=s.get("model", self.config.model),
        )
        self.tracer.emit(
            "llm",
            model=s.get("model", self.config.model),
            input_tokens=s.get("input_tokens", 0),
            output_tokens=s.get("output_tokens", 0),
            latency_ms=round(s.get("latency_ms", 0)),
            cached=s.get("cached", False),
        )

    def run_turn_scoped_stream(
        self,
        user_input: str | None,
        allowed_tools: frozenset[str] | None,
        node_prompt: str | None,
    ):
        """Run ONE scoped turn (Pillar C3): a generator that YIELDS
        the FINAL reply's text tokens as the LLM produces them. Tool rounds run
        silently (no yields). Called from inside the LangGraph nodes, which forward
        the tokens via the stream writer — so LangGraph stays the orchestrator."""
        yield from self._run_turn_stream(user_input, allowed_tools, node_prompt)

    def _run_turn_stream(
        self,
        user_input: str | None = None,
        allowed_tools: frozenset[str] | None = None,
        node_prompt: str | None = None,
    ):
        """The scoped turn: deterministic head, scripted replies, then the LLM tool
        loop streaming the final reply token by token."""
        # Hardcoded greeting (first turn, no input) — the node yields the fixed
        # opening line, not an LLM call. The caller's number is pre-flighted
        # while the greeting plays.
        if user_input is None and self.state.dialog.turn_count == 0:
            self._preflight_phone()
            greeting = self.config.greeting_message
            self.state.messages.append({"role": "assistant", "content": greeting})
            self.state.dialog.turn_count += 1
            self.tracer.emit("agent_reply", text=greeting)
            yield greeting
            return

        # Repeat-guard: snapshot progress BEFORE the deterministic NLU prefill, so a
        # slot/problem filled THIS turn counts as progress and clears the counter.
        self.state.turn.progress_key_at_start = progress_key(self.state)
        self._cancel_requested.clear()  # a stale barge-in never cancels a NEW turn
        # Ticket-node turns skip the diagnosis ingest — without this, the
        # PREVIOUS turn's "supratau" directive leaks into their replies.
        if self.state.ticket.stage:
            self.state.turn.understanding = None

        self.state.dialog.last_heard = (user_input or "").strip()
        from .resolution import detect_turn_intent

        self.state.dialog.last_intent = detect_turn_intent(user_input)
        self._maybe_raise_clarity(user_input)
        # S2 (2026-08-24): a background telemetry read finished while the
        # caller was busy — fold it in at the deterministic turn start, but
        # ONLY as a refresh: in the solution/bridge phase, or when the fresh
        # verdict FLIPS the story, it is discarded (live: the bg read saw the
        # just-plugged PC, the narrative turned foreign_mac mid-bridge and the
        # agent asked "ar keitėte routerį?" over a working bind). The solution
        # steps (dr_see_device / dr_verify) do their own reads at the right
        # moments.
        self._apply_bg_diagnosis()
        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            # The deterministic head may have run EARLIER (diagnose node, A-2
            # 2026-09-07) — the latch prevents a double prefill/guards run.
            if self.state.turn.pre_turn_head_done:
                self.state.turn.pre_turn_head_done = False
            else:
                self._prefill_slots_from_text(user_input)
                self._pre_turn_guards(user_input)

        # The caller's utterance goes on the history for EVERY reply path
        # (review 2026-08-07): scripted turns used to skip it, so the LLM
        # narrator later saw a conversation with holes and re-asked answered
        # questions. One append, up front — the LLM loop below no longer does it.
        if user_input:
            self.state.messages.append({"role": "user", "content": user_input})
            user_input = None

        # Deterministic backstop (before the LLM, so it works with streaming) once a
        # genuine repeat loop has escalated.
        backstop = self._stuck_backstop()
        if backstop is not None:
            yield self._apply_backstop(backstop)
            return

        # Scripted identification-ladder reply (engine-composed, LLM skipped) — the
        # mechanical turns only; off-script turns fall through to the LLM.
        scripted = self._identification_scripted_reply(self.state.dialog.last_heard)
        if scripted is not None:
            yield self._emit_scripted_reply(scripted)
            return

        # D5 (live 2026-08-25: 'Gerai, palauksiu' cost 2.8–12 s of LLM): a bare
        # wait signal at a standing client action is acknowledged scripted.
        wait = self._scripted_wait_ack()
        if wait is not None:
            yield self._emit_scripted_reply(wait)
            return

        max_calls = self.config.max_tool_calls_per_response
        tool_rounds = 0
        while tool_rounds < max_calls:
            self.state.dialog.turn_count += 1
            if self.state.dialog.turn_count > self.state.dialog.max_turns:
                yield self.config.max_turns_message
                return

            # S1 speculation: a precomputed branch reply for the ACTIVE
            # directive skips the LLM entirely — the wording was generated
            # ahead, while the caller was still answering. Consumed only when
            # the drive actually produced the predicted directive.
            injected = self._consume_injected_reply()
            if injected is not None:
                yield injected
                self.state.messages.append({"role": "assistant", "content": injected})
                self._finalize_reply(injected)
                return

            # The user message is already on the history (appended up front, so
            # scripted turns record it too); the prompt builds from history.
            messages = self._build_messages(None, node_prompt, allowed_tools)

            try:
                # Manual consumption instead of `yield from`: the cancel flag is
                # checked BETWEEN TOKENS — closing the inner generator closes the
                # LLM HTTP stream, so the generation itself stops (PR3).
                inner = stream_tool_completion(
                    messages=messages,
                    tools=self._scoped_tools_schema(allowed_tools),
                    tool_choice="auto",
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                streamed: list[str] = []
                while True:
                    try:
                        token = next(inner)
                    except StopIteration as done:
                        message = done.value
                        break
                    if self._cancel_requested.is_set():
                        with suppress(Exception):
                            inner.close()
                        self.on_turn_cancelled("".join(streamed))
                        return
                    if isinstance(token, str):
                        streamed.append(token)
                    yield token
            except Exception as e:
                logger.error(f"LLM stream error: {e}")
                trace_note(self.tracer, self.state, "llm_stream", str(e), level="error")
                yield self.config.error_message
                return

            self._record_llm_stats()

            if message.tool_calls:
                self._execute_tool_calls(message)
                tool_rounds += 1
                continue

            content = (message.content or "").strip()
            if not content:
                # Empty reply (already yielded nothing) -> nudge and retry.
                self.state.messages.append({"role": "assistant", "content": ""})
                self.state.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your last reply was empty. Either call a tool or write a "
                            "non-empty message to the customer."
                        ),
                    }
                )
                tool_rounds += 1
                continue

            # The final reply text was already streamed via `yield from`; persist it
            # to history and run end-of-turn bookkeeping (no extra yield).
            self.state.messages.append({"role": "assistant", "content": content})
            # Registration-claim guard: the narrator said "užregistravau" with no
            # ticket behind it — the contact dialogue starts NOW and its first
            # question rides on the same reply, so the claim becomes true.
            extra = self._registration_claim_guard(content)
            if extra:
                content += extra
                self.state.messages[-1]["content"] = content
                yield extra
            self._finalize_reply(content)
            return

        yield self.config.timeout_message

    def _apply_bg_diagnosis(self) -> None:
        """S2 gate: fold the background telemetry read in ONLY as a refresh —
        in the solution/bridge phase, or when the fresh verdict FLIPS the
        story, it is discarded (the solution steps read at the right moments
        themselves)."""
        bg = self.state.turn.bg_diagnosis
        if not bg:
            return
        self.state.turn.bg_diagnosis = None
        # A-2R (2026-09-07): with no identified customer the telemetry has no
        # one to belong to — after reopen it used to restore the dropped
        # account's diagnosis.
        if not self.state.identity.customer_id:
            return
        with suppress(Exception):
            r0 = self.state.resolution.procedure or {}
            in_solution = bool(
                r0.get("solution_synced")
                or self.state.resolution.bridge_plug_reported
                or self.state.resolution.bridge_bound
            )
            fresh = ((json.loads(bg) or {}).get("verdict") or {}).get("reason")
            current = r0.get("verdict")
            if not in_solution and (not current or fresh == current):
                self._update_state_from_observation("diagnose_connection", bg)
                self.tracer.emit("speculation", action="bg_diagnosis_applied")
            else:
                self.tracer.emit("speculation", action="bg_diagnosis_discarded", fresh=fresh)

    def _consume_injected_reply(self) -> str | None:
        """S1 speculation: the precomputed reply for the ACTIVE directive (set
        by the voice layer when the caller's answer matched a prepared
        branch). Consumed only when the drive actually produced the predicted
        directive — any mismatch falls back to the normal LLM path."""
        inj = self.state.turn.injected_reply
        if not inj:
            return None
        self.state.turn.injected_reply = None
        kind, key, text = inj.get("kind"), inj.get("key"), inj.get("text")
        if not text:
            return None
        if kind == "evidence":
            d = self.state.turn.directives.evidence
            if d and d.get("key") == key:
                self.tracer.emit("speculation", action="hit", kind=kind, key=key)
                return str(text)
        elif (
            kind == "recap"
            and self.state.turn.directives.recap
            or kind == "findings"
            and self.state.turn.directives.findings
        ):
            self.tracer.emit("speculation", action="hit", kind=kind)
            return str(text)
        self.tracer.emit("speculation", action="miss", kind=kind, key=key)
        return None

    def _stuck_backstop(self) -> tuple[str, bool] | None:
        """Deterministic escalation (text, should_close) once the prompt-level nudge
        has failed — fired BEFORE the LLM (so it works with token streaming): at 3
        offer the account code, at 4 register + close. None below that."""
        n = self.state.dialog.stuck_count
        if n >= 4:
            return (_STUCK_REGISTER, True)
        if n >= 3:
            return (_STUCK_OFFER_CODE, False)
        return None

    def _track_stuck(self, reply: str) -> None:
        """Update the stuck counter from this turn's outcome. Increment ONLY when the
        agent actually RE-ASKS the same question (a genuine loop) — a new/different
        question or normal back-and-forth must not escalate. Real progress (a slot/
        customer_id/problem change since the turn started) clears it. Records
        last_question for the next turn's repeat check."""
        progressed = progress_key(self.state) != self.state.turn.progress_key_at_start
        is_q = is_question(reply)
        repeat = bool(
            is_q
            and self.state.dialog.last_question
            and similar(reply, self.state.dialog.last_question)
        )
        self.state.dialog.last_reply_repeated = repeat
        if progressed:
            self.state.dialog.stuck_count = 0
        elif repeat:
            self.state.dialog.stuck_count += 1
        # else: a different question or a statement leaves the counter unchanged —
        # only a real re-ask escalates, and only real progress clears it.
        if is_q:
            self.state.dialog.last_question = reply
        self.tracer.emit("stuck", count=self.state.dialog.stuck_count, repeated=repeat)

    def _identification_scripted_reply(self, user_input: str | None) -> str | None:
        """Deterministic identification-ladder replies (2026-07-31, IDENTIFICATION
        ONLY): the mechanical turns are COMPOSED by the engine from the phrases in
        identification.yaml — the LLM repeatedly reordered or skipped them (promised
        a check without the result, relapsed into confirm rounds, skipped the caller
        question, captured 'Taip.' as a name). An off-script caller turn (a question)
        returns None so the LLM answers it; the ladder resumes next turn. Solving and
        free dialogue never come here."""
        from .identification_flow import identification_scripted_reply

        return identification_scripted_reply(self, user_input)

    def _emit_scripted_reply(self, text: str) -> str:
        """Bookkeeping for an engine-composed reply (mirrors _apply_backstop)."""
        self.state.messages.append({"role": "assistant", "content": text})
        if is_question(text):
            self.state.dialog.last_question = text
        emit_case(self.tracer, self.state)
        self.tracer.emit("scripted", where="identification")
        self.tracer.emit("agent_reply", text=text)
        return text

    def _apply_backstop(self, backstop: tuple[str, bool]) -> str:
        """Emit a deterministic backstop reply (manages the counter itself so a
        repeat backstop climbs 3 -> 4 -> close). Returns the text to yield/return."""
        text, should_close = backstop
        if should_close:
            self.state.closing.case_closed = True
            self.state.closing.closed_reason = "declined"
        else:
            self.state.dialog.stuck_count += 1  # advance the ladder for the next turn
        self.state.messages.append({"role": "assistant", "content": text})
        if is_question(text):
            self.state.dialog.last_question = text
        self._maybe_end_on_goodbye(text)
        emit_case(self.tracer, self.state)
        self.tracer.emit("stuck", count=self.state.dialog.stuck_count, repeated=False)
        self.tracer.emit("agent_reply", text=text)
        return text

    def _maybe_raise_clarity(self, user_input: str | None) -> None:
        """Once the caller says they do not follow the wording ("kas tas WAN?"),
        stay in plain language for the rest of the call. One-way: a caller who was
        lost once should not be dropped back into jargon two steps later."""
        from .resolution import detect_confusion

        if self.state.dialog.clarity_level == "standard" and detect_confusion(user_input):
            self.state.dialog.clarity_level = "basic"

    def _maybe_end_on_goodbye(self, text: str) -> None:
        """Delegates to closing_flow.maybe_end_on_goodbye (R3 extraction)."""
        from .closing_flow import maybe_end_on_goodbye

        maybe_end_on_goodbye(self, text)

    def _finalize_reply(self, text: str) -> None:
        """Shared end-of-turn bookkeeping for a customer-facing reply: update the
        repeat-guard, emit the case snapshot + the reply trace."""
        self._track_stuck(text)
        self._maybe_end_on_goodbye(text)
        emit_case(self.tracer, self.state)
        self.tracer.emit("agent_reply", text=text)
