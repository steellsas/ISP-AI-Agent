"""
Agent - ISP Customer Support

Drives the support conversation with native LLM function/tool calling.

Loop (run_until_response):
1. The model receives the conversation + tool schemas (tool_choice="auto").
2. It either calls one or more tools (structured tool_calls) or replies in text.
3. Tool results are fed back as role:"tool" messages and the model continues.
4. When the model replies with text (no tool call), that is the customer answer.

The class is still named ReactAgent for import compatibility; the brittle
"Thought:/Action:/Action Input:" regex parsing has been replaced by native
tool calls (see agent.tools.get_tools_schema and services.llm.llm_tool_completion).

Usage:
    from agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060012345")
    response = agent.run_until_response("Neveikia internetas")
    uv run python -m src.agent.react_agent --lang lt --phone +37060012345
"""

import json
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

# LLM client
from src.services.llm.client import (
    get_last_call_stats,
    llm_tool_completion,
    stream_tool_completion,
)

from .config import AgentConfig, create_config
from .prompts import load_system_prompt
from .state import AgentState

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
    from .tools import execute_tool, get_tools_description, get_tools_schema

    USING_REAL_TOOLS = True
except ImportError:
    USING_REAL_TOOLS = False
    TOOLS = []

    def get_tools_description():
        return "No tools available"

    def get_tools_schema():
        return []

    def execute_tool(name, args):
        return json.dumps({"error": "Tools not available"})


logger = logging.getLogger(__name__)

# Closing rules moved to closing_flow.py (R3, docs/ROADMAP_REFACTORING.md §4);
# the alias keeps existing imports/tests working during the migration.


def _register_linear_strategies() -> None:
    """Populate STRATEGIES with a linear guided walk for each LINEAR_DOCS verdict
    (reads the doc's step count once), so a purely linear fault needs ONLY a RAG doc
    — no bespoke strategy code. No-op while LINEAR_DOCS is empty."""
    try:
        from .playbook import step_count
        from .resolution import LINEAR_DOCS, STRATEGIES, build_linear_strategy

        for verdict, doc in LINEAR_DOCS.items():
            if verdict in STRATEGIES:
                continue
            n = step_count(doc)
            if n > 0:
                STRATEGIES[verdict] = build_linear_strategy(verdict, doc, n)
    except Exception:  # pragma: no cover - best-effort, never break import
        pass


_register_linear_strategies()

# Verdict glossaries moved to glossary.py (R3); aliases keep call sites working.

# Repeat-guard: politeness/acknowledgement words stripped before comparing two
# questions, so "Atsiprašau, ar galėtumėte ..." matches "Ar galėtumėte ..." as a
# verbatim re-ask instead of looking different because of the prefix.
_STUCK_FILLER = {
    "atsiprašau",
    "gerai",
    "supratau",
    "prašau",
    "ačiū",
    "sakykite",
    "pasakykite",
}

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

        self.state = AgentState(
            caller_phone=caller_phone,
            max_turns=self.config.max_turns,
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

        # Streets/localities registry for deterministic NLU prefill (loaded lazily
        # on the first user turn so construction stays DB-free where possible).
        self._registry: tuple[list[str], list[str]] | None = None

        # Per-turn guards (set in _pre_turn_guards): address-offer commit veto note and
        # the one-turn "identification reopened" note.
        self._addr_confirm_note: str | None = None
        self._reopen_note = False
        # Identification ladder: True while the check result is deferred behind the
        # caller-intro question ("su kuo kalbu?"); cleared once the result is narrated.
        self._result_pending = False
        # Set when the ENGINE just committed the identity this turn — the scripted
        # ladder reply then opens with the address echo.
        self._just_identified = False
        # Farewell-mid-process clarify contract (2026-08-03): the confirm question is
        # pending / the walker holds one turn after the caller decides to continue.
        self._end_confirm_pending = False
        self._resume_hold = False
        # Bind discipline (2026-08-04): the bridge bind ran — never repeat it.
        self._bridge_bound = False
        # The bridge OFFER was spoken (drive path) — the first fix deferral says
        # the transition + offer; later deferrals say the short wait line.
        self._drive_bridge_offered = False
        # Evidence ledger (Ledger v1): a freshly detected client-client conflict
        # (key, old, new) — the next scripted reply asks ONE clarification; the
        # key whose clarification is out, awaiting the settling answer.
        self._evidence_conflict: tuple[str, str, str] | None = None
        self._evidence_conflict_asked: str | None = None
        # W1-2 svarbos vartai: a NEW volunteered fact that flips the story is
        # parked here until one confirm question settles it (STT garbles
        # poison exactly these — "rozetė NEVEIKĖ" heard live for a fine outlet).
        self._fact_confirm: tuple[str, str] | None = None
        self._fact_confirm_asked: tuple[str, str] | None = None
        # Barge-in cancel (Phase 5 PR3): set via request_cancel() from any
        # thread; the streaming token loop checks it BETWEEN TOKENS — the LLM
        # stream closes mid-generation and the cancelled-turn bookkeeping runs
        # (partial reply recorded, interrupted question re-asked). LangGraph
        # runs the node to completion in the background, so an outer
        # generator-close never reaches this loop — the flag is the only
        # reliable cancel path (verified 2026-08-06).
        self._cancel_requested = False
        # Side-topic node (2026-08-07): an off-fault QUESTION during analysis /
        # solving freezes the engine for the turn (nothing advances on side
        # chatter); the 3rd consecutive deviation gets the scripted frame.
        self._side_topic_this_turn = False
        self._side_topic_turns = 0
        # The understanding pass' read of the CURRENT turn (None = pass skipped
        # or failed -> keyword fallback ran instead).
        self._last_understanding: dict | None = None
        # R4 perception merge: the understanding call's step-classification read
        # ({step_id, input, obs}) — consumed by the walker's classify guards so
        # an asked-step turn costs ONE sensor call, not two.
        self._perception_step: dict | None = None
        # Persona (R5c): the evidence question as a narrator GOAL directive
        # ({key, reikia, kodel, klausimas}) — set by the drive, consumed by the
        # facts block, reset every turn at ingest.
        self._evidence_directive: dict | None = None
        self._findings_directive: dict | None = None
        self._recap_directive: dict | None = None
        self._ticket_directive: dict | None = None
        self._ident_directive: dict | None = None
        # S1 speculation (2026-08-24): the branch cache prepared while the
        # caller was answering, and the matched reply injected past the LLM.
        self._spec_cache: dict | None = None
        self._injected_reply: dict | None = None
        self._bg_diagnosis: str | None = None  # S2: background telemetry read
        # Findings announce: spoken ONCE at the first confirmed-hypothesis
        # moment; stashed when the reply comes from another layer that turn.
        self._findings_announced = False
        self._pending_announce = ""
        # Bare-"ne" escalate clarify (2026-08-11): asked at most once per case;
        # pending = the scripted choice question goes out this turn.
        self._escalate_clarify_asked = False
        self._escalate_clarify_pending = False
        # Ticket refusal with solving content: one-turn narrator directive to
        # say "neregistruoju" and return to the last fix instruction.
        self._resume_fix_note = False
        self._resync_note = False
        # D1 delivery ledger: the tail of an interrupted reply the caller never
        # HEARD — surfaced to the narrator next turn, then cleared.
        self._undelivered_tail: str | None = None
        # W1-1: the opening already carried the anamnesis — the narrator shows
        # it HEARD ("aišku — nuo vakar") instead of re-asking; one-shot.
        self._opening_heard_note = False
        # W2 tylusis analitikas: background advisory notes for the narrator's
        # next turn (written by the bg thread, consumed once in facts).
        self._analyst_notes: list[str] | None = None
        # D1+ (Andrius 2026-08-26): the interrupted reply's QUESTION never
        # sounded — the narrator must react to the caller and RE-ASK it.
        self._unheard_question: str | None = None
        # Pasitikslinimo checkpoints (2026-08-11): facts recap before the first
        # announce; refute confirm before a client-fact pivot; the pending-key
        # whose done-report ("patikrinau") carried no result this turn.
        self._recap_state = ""
        self._refute_state = ""
        self._done_report_key: str | None = None
        # Plug-report memory (round 4): the caller's completed-plug report,
        # remembered across turns — the bind gate no longer demands the plug
        # verb in THIS turn's utterance.
        self._bridge_plug_reported = False
        # Bridge-failure ladder (round 5): 0 = cable re-check, 1 = the LAN
        # question went out, 2 = escalate with the attempt on the ticket.
        self._bridge_fail_stage = 0
        self._bridge_fail_note: str | None = None
        # Given-up keys already revived once (round 6) — never a second time.
        self._revived_keys: set[str] = set()
        # How many times each evidence question was asked (level 1 -> paprasciau
        # -> give up and mark "neaišku"), so an unreadable caller never loops us.
        self._evidence_asks: dict[str, int] = {}
        # Ticket-confirmation dialogue (2026-08-04): every registration first collects
        # the contact number (ALWAYS asked, never assumed) and when to call. Stage is
        # None | "phone" | "hours" | "done"; ctx remembers the escalate step to build
        # the ticket from once the dialogue completes.
        # _ticket_stage lives on AgentState (see the property below) — no init needed.
        self._ticket_ctx: dict | None = None
        # This turn's utterance is an off-script QUESTION during the dialogue
        # ("kokiu numeriu?") — the ticket node's LLM answers it (with the pending
        # stage question re-asked); the stage does not advance.
        self._ticket_offscript = False
        # INFORM arc: the news (billing/outage) was already delivered once — the JAU
        # PRANEŠTA marker stops the model re-reading it every turn.
        self._news_told = False

        # Per-node scoping (LangGraph step 3.2): a graph node may restrict the
        # tools exposed to the model and add a focused prompt. None = unrestricted
        # (the legacy single-agent behaviour).
        self._active_tool_names: frozenset[str] | None = None
        self._node_prompt: str | None = None
        self._active_node: str | None = None  # which graph node is running (debug)
        # Shadow-solver safeguard counters (Phase 3.8 step 3) — fed to the gate.
        self._solver_prev_step: str | None = None
        self._solver_cycles = 0
        self._solver_low_conf = 0
        self._solver_internal_hops = 0

        # Repeat-guard bookkeeping (set per turn). _turn_start_key snapshots the
        # progress fields at the start of a turn so the finalizer can tell whether
        # the turn advanced; _repeated_verbatim flags a near-identical re-ask.
        self._turn_start_key: tuple | None = None
        self._repeated_verbatim: bool = False

        # DB-grounded address note (set per turn from the accumulated slots): the
        # DB's verdict on everything heard so far, surfaced so the agent is steered
        # by what the DB actually holds, not by the last garbled fragment.
        self._db_address_note: str | None = None

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

    @property
    def _ticket_stage(self) -> str | None:
        """Promoted to AgentState.ticket_stage (R3, roadmap §6): the state owns
        the value (checkpointed, read by the v2 entry router); this property
        keeps every existing engine call site working unchanged."""
        return self.state.ticket_stage

    @_ticket_stage.setter
    def _ticket_stage(self, value: str | None) -> None:
        self.state.ticket_stage = value

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

    def _build_messages(self, user_input: str = None) -> list:
        """Delegates to narrator_flow.build_messages (R3 extraction)."""
        from .narrator_flow import build_messages

        return build_messages(self, user_input)

    # Security-sensitive resolution actions — only exposed on the strategy STEP
    # that permits them (update_mac on bind_mac, create_ticket on escalate). So the
    # model cannot bind a device during a CONFIRM step, before the caller confirms.
    _STRATEGY_ACTION_TOOLS = frozenset({"update_mac", "reset_port", "create_ticket"})
    # Diagnostics the ENGINE owns during a strategy — the model must not call them
    # (observed: it looped check_network_status / run_ping_test instead of talking).
    _STRATEGY_DIAG_TOOLS = frozenset(
        {"diagnose_connection", "check_network_status", "run_ping_test", "check_port_status"}
    )

    def _scoped_tools_schema(self) -> list:
        """Delegates to narrator_flow.scoped_tools_schema (R3 extraction)."""
        from .narrator_flow import scoped_tools_schema

        return scoped_tools_schema(self)

    def run_turn_scoped(
        self,
        user_input: str | None,
        allowed_tools: frozenset[str] | None,
        node_prompt: str | None,
    ) -> str:
        """Run ONE turn restricted to `allowed_tools` with a focused `node_prompt`
        appended (used by the LangGraph nodes). Scoping is reset afterwards so the
        engine returns to its unrestricted default."""
        self._active_tool_names = allowed_tools
        self._node_prompt = node_prompt
        try:
            return self.run_until_response(user_input)
        finally:
            self._active_tool_names = None
            self._node_prompt = None

    def _prune_history(self, messages: list) -> list:
        """Delegates to narrator_flow.prune_history (R3 extraction)."""
        from .narrator_flow import prune_history

        return prune_history(self, messages)

    def _state_facts_block(self) -> str | None:
        """Delegates to narrator_flow.state_facts_block (R3 extraction)."""
        from .narrator_flow import state_facts_block

        return state_facts_block(self)

    @staticmethod
    def _assistant_tool_message(message: Any) -> dict:
        """
        Serialize an assistant message that requested tool calls into the dict
        shape the chat API needs echoed back on the next turn.

        The protocol requires that, before any role:"tool" result messages, the
        exact assistant message that issued the tool_calls is present in history
        (matched by tool_call_id). We store a plain dict (not the litellm object)
        so the history stays JSON-serializable.
        """
        return {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        }

    # Technical tools that must NOT run before the customer is identified
    # (Phase 3.5 §5 tool-access gate). Read-only lookups stay open pre-id.
    _GATED_TOOLS = frozenset({"diagnose_connection", "update_mac", "reset_port", "create_ticket"})

    # Line/provider-side faults that a remote or instructed fix is supposed to
    # clear. If a fresh diagnose still shows one of these, the fix has NOT taken —
    # so "resolved" is premature (telemetry is the source of truth, not the
    # caller's word). healthy_to_router is deliberately absent: the line is fine,
    # any remaining fault is client-side (Wi-Fi/device) which telemetry can't see,
    # so that close is the caller's call.
    _UNRESOLVED_LINE_FAULTS = frozenset(
        {"foreign_mac", "link_down_local", "dhcp_silent", "crc_errors", "no_mac_observed"}
    )

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

    def _emit_decision(self, before: str | None) -> None:
        """One line per strategy turn: what the caller's turn was read as, where the
        walker went (or that it HELD), and the live hypothesis. This is the 'why' the
        raw reply never showed — e.g. step=None means no strategy is active at all."""
        s = self.state
        r = s.resolution
        after = r.get("step") if r else None
        if before is None and after is None:
            return  # no strategy in play — nothing to explain
        if s.case_closed:
            action, dest = "close", s.closed_reason
        elif after == before:
            action, dest = "hold", after
        else:
            action, dest = "advance", after
        h = s.hypothesis or {}
        self.tracer.emit(
            "decision",
            intent=s.last_intent or None,
            awaiting=s.awaiting,
            action=action,
            from_step=before,
            to=dest,
            hypothesis=h.get("cause"),
            hyp_status=h.get("status"),
        )

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
        """Ask the running streaming turn to stop (thread-safe: a bool flip).
        Checked between tokens; a no-op when no turn is running (the flag is
        reset at the next turn's start)."""
        self._cancel_requested = True

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
        key = getattr(self, "_evidence_last_ask_key", None)
        if key and self._evidence_asks.get(key, 0) > 0:
            self._evidence_asks[key] -= 1
        self.tracer.emit("turn_cancelled", spoken=spoken[:160])

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
        self._undelivered_tail = tail or None
        # Andrius 2026-08-26: the agent must NEVER believe it asked a question
        # the caller could not hear. When the "?" lives only in the unheard
        # tail, the ask never happened: the pending evidence key and its ask
        # counter roll back (the caller's next words are NOT an answer to it),
        # the step's presented counter steps back, and the narrator gets a
        # STRONG re-ask directive instead of the advisory tail note.
        if "?" in tail and "?" not in heard:
            s.last_question = None
            key = getattr(self, "_evidence_last_ask_key", None)
            if key:
                if self._evidence_asks.get(key, 0) > 0:
                    self._evidence_asks[key] -= 1
                self._evidence_last_ask_key = None
            r = s.resolution or {}
            pres = r.get("presented") or {}
            step_id = r.get("step")
            if step_id and pres.get(step_id, 0) > 0:
                pres[step_id] -= 1
            self._unheard_question = tail
            self._undelivered_tail = None  # superseded by the strong directive
        self.tracer.emit(
            "delivery",
            delivered=delivered,
            total=total,
            unheard=tail[:160],
            question_unheard=bool(getattr(self, "_unheard_question", None)),
        )

    def _commit_driven_reply(self, user_input: str | None, reply: str) -> str:
        """End-of-turn bookkeeping for an engine/solver-driven reply (mirrors the
        walker path's run_turn_scoped): user_turn trace, dialogue history, shared
        finalisation (case snapshot + agent_reply)."""
        if user_input:
            self.state.last_heard = user_input.strip()
            self.tracer.emit("user_turn", text=user_input)
            self.state.messages.append({"role": "user", "content": user_input})
        self.state.messages.append({"role": "assistant", "content": reply})
        self._finalize_reply(reply)
        return reply

    # Evidence-drive flow moved to evidence_drive.py (R3, roadmap §4) — thin
    # delegates keep every internal call site and test working unchanged.

    def _revive_gave_up_key(self, spec: dict) -> str | None:
        """Delegates to evidence_drive.revive_gave_up_key (R3 extraction)."""
        from .evidence_drive import revive_gave_up_key

        return revive_gave_up_key(self, spec)

    def _maybe_facts_recap(self) -> str | None:
        """Delegates to evidence_drive.maybe_facts_recap (R3 extraction)."""
        from .evidence_drive import maybe_facts_recap

        return maybe_facts_recap(self)

    def _refuting_client_fact(self, spec: dict) -> tuple[str, str] | None:
        """Delegates to evidence_drive.refuting_client_fact (R3 extraction)."""
        from .evidence_drive import refuting_client_fact

        return refuting_client_fact(self, spec)

    def _maybe_refute_confirm(self, spec: dict) -> str | None:
        """Delegates to evidence_drive.maybe_refute_confirm (R3 extraction)."""
        from .evidence_drive import maybe_refute_confirm

        return maybe_refute_confirm(self, spec)

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

    def _last_agent_question(self) -> str | None:
        """The last thing the agent actually said — the real question the caller is
        answering (a better classifier context than the English step hint)."""
        for m in reversed(self.state.messages):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                return m["content"]
        return None

    def _asked_recently(self, r: dict) -> bool:
        """True when the current step's question actually went out within the
        last ~3 exchanges. Steps presented long ago (walker benched by the
        solver/evidence drive) may not read new replies as their answers —
        test/legacy setups without the stamp count as fresh."""
        at = r.get("asked_at")
        if at is None:
            return True
        return len(self.state.messages) - at <= 6

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

    def _register_ticket_from_state(self, step) -> None:
        """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
        cause from the hypothesis/verdict, actions from this call's trace — never from
        the model's free text (which once invented an invalid ticket_type). Idempotent:
        an existing ticket is never duplicated. Best-effort: a failure is traced and the
        close still proceeds (the call record keeps the outcome)."""
        from .executor_flow import register_ticket_from_state

        register_ticket_from_state(self, step)

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

    def _gate_tool(self, name: str, args: dict) -> str | None:
        """
        Deterministic tool-access gate.

        Returns a corrective observation (JSON string) when a technical tool is
        called before identification, or with a customer_id that is not the
        identified one — otherwise None (the call proceeds). This moves the "no
        diagnostics before identification" / "never act on a guessed id" rules
        out of the prompt and into code, so a hallucinated `diagnose_connection`
        cannot fire (observed: customer_id='1' on an unidentified caller).
        """
        from .executor_flow import gate_tool

        return gate_tool(self, name, args)

    def _update_state_from_observation(self, action: str, observation: str):
        """Delegates to narrator_flow.update_state_from_observation (R3 extraction)."""
        from .narrator_flow import update_state_from_observation

        return update_state_from_observation(self, action, observation)

    def _trace_tool_result(self, name: str, observation: str, ms: int | None = None) -> None:
        """Emit a tool_result event (+ a dedicated verdict event for diagnoses).

        Keeps the trace small: a boolean ok + a few key fields + how long the
        tool took (ms) — needed to know which tool to overlap/mask. The verdict
        is its own event type because "why the agent acted" is the most valuable
        thing when debugging.
        """
        try:
            data = json.loads(observation)
        except (json.JSONDecodeError, TypeError):
            self.tracer.emit("tool_result", name=name, ok=None, ms=ms, summary="<non-json>")
            return

        ok = data.get("success")
        summary: dict[str, Any] = {}
        for key in ("customer_id", "ticket_id", "outcome"):
            if data.get(key):
                summary[key] = data[key]
        if not ok and data.get("error"):
            summary["error"] = data["error"]
        # resolve_address: surface the per-level hint (drives the next question).
        if name == "resolve_address" and data.get("hint"):
            summary["hint"] = data["hint"]

        self.tracer.emit("tool_result", name=name, ok=ok, ms=ms, summary=summary or None)

        # diagnose_connection carries the verdict -> its own event.
        verdict = data.get("verdict") if isinstance(data, dict) else None
        if verdict:
            self.tracer.emit(
                "verdict",
                side=verdict.get("side"),
                group=verdict.get("group"),
                action=verdict.get("action"),
                reason=verdict.get("reason"),
            )

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

    def _revalidate_accumulated_address(self) -> None:
        """Check the ACCUMULATED address slots against the DB every turn and stash
        the DB's verdict for the facts block.

        The tools can always validate what is real — which streets exist, in which
        village, which house numbers are on a street — so we lean on that instead
        of the last (often garbled) fragment. resolve_address is called with ALL
        slots gathered so far, in any order; its `hint` already says the exact next
        step ("Radau sutartį adresu … — patvirtink", "Paklausk namo numerio",
        "Dainų ar Dailės?", "Namo 6 … nerandu"). Read-only: the id is committed only
        when the agent confirms with the caller (anchor rule), never here.
        """
        from .identification_flow import revalidate_accumulated_address

        revalidate_accumulated_address(self)

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
        if s.customer_id and not s.ticket_id and not s.case_closed and s.resolution is not None:
            from .resolution import get_strategy

            # The line's CURRENT truth decides (2026-08-06): a caller who hung up
            # right after "veikia!" must NOT get a technician ticket (observed
            # live: TKT00D19E54 for a healthy line). A recorded fix or one fresh
            # diagnose read showing healthy skips the net; telemetry unreachable
            # -> register anyway (a spare ticket beats an abandoned caller).
            solved = bool(s.resolution.get("telemetry_fixed"))
            if not solved:
                try:
                    d = json.loads(
                        execute_tool("diagnose_connection", {"customer_id": s.customer_id})
                    )
                    solved = ((d.get("verdict") or {}).get("reason") or "healthy_to_router") == (
                        "healthy_to_router"
                    )
                except Exception:  # pragma: no cover - defensive
                    solved = False
            if solved:
                s.case_closed = True
                s.closed_reason = "resolved"
                self.tracer.emit("decision", intent="hangup_net", action="skip_solved")
            else:
                s.resolution.setdefault(
                    "escalate_reason", "Pokalbis nutrūko — klientas padėjo ragelį."
                )
                if not s.contact_phone:
                    s.contact_phone = s.caller_phone
                if not s.contact_hours:
                    s.contact_hours = "bet kada"
                strat = get_strategy(s.resolution.get("verdict"))
                esc = strat.step("escalate") if strat else None
                self._register_ticket_from_state(esc)
                if s.ticket_id:
                    s.closed_reason = "registered"
                    self.tracer.emit("decision", intent="hangup_net", action="register")
        # Structured OUTCOME of the call, built DETERMINISTICALLY from state (Phase 3.10):
        # why they called, the cause + side, what ran, resolved?/ticket, who called. Emitted
        # for the record/reports; DB persistence to the conversations table is a follow-up.
        summary = self._build_call_summary()
        self.tracer.emit("call_summary", **summary)
        self.tracer.emit(
            "session_end",
            outcome=outcome or summary.get("outcome"),
            customer_id=self.state.customer_id,
            ticket_id=self.state.ticket_id,
            turn_count=self.state.turn_count,
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
                customer_id=self.state.customer_id,
                messages=self.state.messages,
                outcome=outcome or summary.get("outcome"),
                summary=summary,
                ticket_id=self.state.ticket_id,
            )
        except Exception as e:  # pragma: no cover - defensive
            self._trace_note("persist_call_record", f"failed: {e}", level="warn")

    def _build_call_summary(self) -> dict:
        """The call's outcome, derived from state — the single source for the record and
        (later) the ticket. No LLM, no new reasoning: it only reports what the engine knows.
        `actions` come from the tool_calls in this session's trace."""
        s = self.state
        net = s.diagnosis.get("network") or {}
        h = s.hypothesis or {}
        cause = h.get("cause") or (s.resolution or {}).get("verdict") or net.get("reason")
        return {
            "purpose": s.problem_type,
            "customer_id": s.customer_id,
            "address": s.customer_address,
            "caller_name": s.caller_name,
            "caller_relation": s.caller_relation,
            "anamnesis": (
                {"raw": s.anamnesis_raw, "when": s.anamnesis_when, "trigger": s.anamnesis_trigger}
                if s.anamnesis_raw
                else None
            ),
            "cause": cause,
            "side": net.get("side"),  # provider | customer | unclear
            "outcome": s.closed_reason,  # resolved | outage | declined | escalated | None
            "resolved": s.closed_reason == "resolved",
            "ticket_id": s.ticket_id,
            "actions": self._tools_called_this_session(),
            # F4 (Andrius 2026-08-20): a call that ended WITHOUT identification
            # records everything that was heard — the address may have changed
            # its name, the caller may not be the holder; a person reading the
            # record (or the caller phoning back) can pick the thread up.
            "identifikacija_nepavyko": (
                {
                    "girdeta": list(s.heard_utterances)[-6:],
                    "gatve": s.profile.street.value,
                    "namas": s.profile.house.value,
                    "miestas": s.profile.city.value,
                }
                if not s.customer_id and s.problem_type
                else None
            ),
        }

    def _tools_called_this_session(self) -> list[str]:
        """Tool names actually executed this call, read from the session's own trace
        (single source of truth; append-only, safe to read at end)."""
        path = getattr(self.tracer, "path", None)
        if not path:
            return []
        seen: list[str] = []
        try:
            import json as _json
            from pathlib import Path as _Path

            for line in _Path(path).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                e = _json.loads(line)
                if e.get("type") == "tool_call" and e.get("name") and e["name"] not in seen:
                    seen.append(e["name"])
        except Exception:  # pragma: no cover - best-effort; the summary still emits
            pass
        return seen

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
        """Streaming variant of run_turn_scoped (Pillar C3): a generator that YIELDS
        the FINAL reply's text tokens as the LLM produces them. Tool rounds run
        silently (no yields). Called from inside the LangGraph nodes, which forward
        the tokens via the stream writer — so LangGraph stays the orchestrator."""
        self._active_tool_names = allowed_tools
        self._node_prompt = node_prompt
        try:
            yield from self._run_until_response_stream(user_input)
        finally:
            self._active_tool_names = None
            self._node_prompt = None

    def _run_until_response_stream(self, user_input: str | None = None):
        """Like run_until_response, but streams the final reply token by token."""
        # Hardcoded greeting (first turn, no input) — mirrors run_until_response so
        # the streaming node yields the fixed opening line, not an LLM call.
        if user_input is None and self.state.turn_count == 0:
            self._preflight_phone()
            greeting = self.config.greeting_message
            self.state.messages.append({"role": "assistant", "content": greeting})
            self.state.turn_count += 1
            self.tracer.emit("agent_reply", text=greeting)
            yield greeting
            return

        # Repeat-guard: snapshot progress BEFORE the deterministic NLU prefill, so a
        # slot/problem filled THIS turn counts as progress and clears the counter.
        self._turn_start_key = self._progress_key()
        self._cancel_requested = False  # a stale barge-in never cancels a NEW turn
        # Ticket-node turns skip the diagnosis ingest — without this, the
        # PREVIOUS turn's "supratau" directive leaks into their replies.
        if self._ticket_stage:
            self._last_understanding = None

        self.state.last_heard = (user_input or "").strip()
        from .resolution import detect_turn_intent

        self.state.last_intent = detect_turn_intent(user_input)
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
        scripted = self._identification_scripted_reply(self.state.last_heard)
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
            self.state.turn_count += 1
            if self.state.turn_count > self.state.max_turns:
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
            messages = self._build_messages(None)

            try:
                # Manual consumption instead of `yield from`: the cancel flag is
                # checked BETWEEN TOKENS — closing the inner generator closes the
                # LLM HTTP stream, so the generation itself stops (PR3).
                inner = stream_tool_completion(
                    messages=messages,
                    tools=self._scoped_tools_schema(),
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
                    if self._cancel_requested:
                        with suppress(Exception):
                            inner.close()
                        self.on_turn_cancelled("".join(streamed))
                        return
                    if isinstance(token, str):
                        streamed.append(token)
                    yield token
            except Exception as e:
                logger.error(f"LLM stream error: {e}")
                self._trace_note("llm_stream", str(e), level="error")
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
        bg = getattr(self, "_bg_diagnosis", None)
        if not bg:
            return
        self._bg_diagnosis = None
        with suppress(Exception):
            r0 = self.state.resolution or {}
            in_solution = bool(
                r0.get("solution_synced")
                or getattr(self, "_bridge_plug_reported", False)
                or getattr(self, "_bridge_bound", False)
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
        inj = getattr(self, "_injected_reply", None)
        if not inj:
            return None
        self._injected_reply = None
        kind, key, text = inj.get("kind"), inj.get("key"), inj.get("text")
        if not text:
            return None
        if kind == "evidence":
            d = getattr(self, "_evidence_directive", None)
            if d and d.get("key") == key:
                self.tracer.emit("speculation", action="hit", kind=kind, key=key)
                return str(text)
        elif (
            kind == "recap"
            and getattr(self, "_recap_directive", None)
            or kind == "findings"
            and getattr(self, "_findings_directive", None)
        ):
            self.tracer.emit("speculation", action="hit", kind=kind)
            return str(text)
        self.tracer.emit("speculation", action="miss", kind=kind, key=key)
        return None

    def step(self, user_input: str = None) -> dict[str, Any]:
        """
        Execute one agent step.

        Args:
            user_input: Customer message (None for initial/continuation)

        Returns:
            Dict with: thought, action, action_input, observation, response, is_complete
        """
        self.state.turn_count += 1

        # Check turn limit
        if self.state.turn_count > self.state.max_turns:
            return {
                "thought": "Max turns reached",
                "action": "finish",
                "response": self.config.max_turns_message,
                "is_complete": True,
            }

        # Build messages and call LLM
        messages = self._build_messages(user_input)

        if user_input:
            self.state.messages.append({"role": "user", "content": user_input})

        try:
            message = llm_tool_completion(
                messages=messages,
                tools=self._scoped_tools_schema(),
                tool_choice="auto",
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

            # Track LLM stats
            stats = get_last_call_stats()
            self.llm_stats.add_call(
                input_tokens=stats.get("input_tokens", 0),
                output_tokens=stats.get("output_tokens", 0),
                cost=stats.get("cost", 0),
                latency_ms=stats.get("latency_ms", 0),
                cached=stats.get("cached", False),
                model=stats.get("model", self.config.model),
            )
            # One LLM call per step -> trace its tokens/latency (where agent_ms goes).
            self.tracer.emit(
                "llm",
                model=stats.get("model", self.config.model),
                input_tokens=stats.get("input_tokens", 0),
                output_tokens=stats.get("output_tokens", 0),
                latency_ms=round(stats.get("latency_ms", 0)),
                cached=stats.get("cached", False),
            )

        except Exception as e:
            logger.error(f"LLM error: {e}")
            self._trace_note("llm", str(e), level="error")
            return {
                "thought": f"LLM Error: {e}",
                "action": "error",
                "response": self.config.error_message,
                "is_complete": False,
            }

        result = {
            "thought": None,
            "action": None,
            "action_input": None,
            "observation": None,
            "response": None,
            "is_complete": False,
            "needs_continuation": False,
            "tool_calls": [],
        }

        tool_calls = getattr(message, "tool_calls", None)

        if tool_calls:
            # The model chose to call one or more tools. Echo the assistant message,
            # run each tool, append results — no customer-facing reply yet →
            # needs_continuation so run_until_response loops.
            executed = self._execute_tool_calls(message)
            result["tool_calls"] = executed
            # Back-compat single-action view (last tool) for existing callers/UI.
            result["action"] = executed[-1]["name"] if executed else None
            result["action_input"] = executed[-1]["arguments"] if executed else None
            result["observation"] = executed[-1]["observation"] if executed else None
            result["needs_continuation"] = True
            return result

        # No tool calls → the content is the reply for the customer.
        content = (message.content or "").strip()

        # Model failure mode: no tool call AND no text. An empty reply gives the
        # customer nothing, so nudge the model with a corrective turn and let the
        # loop retry (bounded by max_tool_calls_per_response → no infinite loop /
        # cost blowup). result["response"] stays None so run_until_response does
        # not treat this as a real answer.
        if not content:
            logger.warning(
                "[AGENT] Empty reply with no tool call; injecting correction and retrying"
            )
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
            result["needs_continuation"] = True
            return result

        result["action"] = "respond"
        result["response"] = content
        self.state.messages.append({"role": "assistant", "content": content})
        return result

    def run_until_response(
        self,
        user_input: str = None,
        max_tool_calls: int = None,
    ) -> str:
        """
        Run agent until it has a response for the customer.

        Args:
            user_input: Customer message (None for initial greeting)
            max_tool_calls: Max tool calls before forcing response

        Returns:
            Agent response string
        """
        # Hardcoded greeting - first message without user input
        if user_input is None and self.state.turn_count == 0:
            # Pre-flight the caller's number while the greeting plays — by the
            # customer's first turn the phone account is already known.
            self._preflight_phone()

            greeting = self.config.greeting_message

            # Log to message history (for context)
            self.state.messages.append({"role": "assistant", "content": greeting})
            self.state.turn_count += 1

            logger.info(f"[AGENT] Hardcoded greeting: {greeting}")
            self.tracer.emit("agent_reply", text=greeting)
            return greeting

        # Repeat-guard: snapshot progress BEFORE the NLU prefill (so a slot filled
        # this turn counts as progress and clears the counter).
        self._turn_start_key = self._progress_key()

        self.state.last_heard = (user_input or "").strip()
        from .resolution import detect_turn_intent

        self.state.last_intent = detect_turn_intent(user_input)
        self._maybe_raise_clarity(user_input)
        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            # Deterministic NLU prefill (Track A) before the LLM sees the turn.
            self._prefill_slots_from_text(user_input)
            self._pre_turn_guards(user_input)

        # Deterministic backstop before the LLM, once a genuine repeat loop escalated.
        backstop = self._stuck_backstop()
        if backstop is not None:
            return self._apply_backstop(backstop)

        # Scripted identification-ladder reply (engine-composed, LLM skipped).
        scripted = self._identification_scripted_reply(user_input)
        if scripted is not None:
            return self._emit_scripted_reply(scripted)

        # Normal LLM flow
        max_calls = max_tool_calls or self.config.max_tool_calls_per_response
        tool_calls = 0

        while tool_calls < max_calls:
            result = self.step(user_input)
            user_input = None  # Only pass on first step

            # Distinguish "no response yet" (None) from a real reply. An empty
            # respond is now caught in step() (needs_continuation), so any
            # non-None response here is a genuine answer for the customer.
            if result.get("response") is not None:
                return self._reply(result["response"])

            if result.get("is_complete"):
                reply = result.get("response", self.config.conversation_end_message)
                self.end_session(outcome="complete")
                return self._reply(reply)

            if result.get("needs_continuation"):
                tool_calls += 1
                continue

            break

        return self._reply(self.config.timeout_message)

    # --- Repeat-guard ------------------------------------------------------

    def _progress_key(self) -> tuple:
        """A snapshot of the fields that mean the conversation ADVANCED. Compared
        start-vs-end of a turn: if it changed, the turn made real progress (a slot
        filled, identified, an outage found, the case closed) — so the stuck
        counter resets. Text changing alone is NOT progress (docs: reset on state,
        not on a reworded question)."""
        p = self.state.profile
        filled = sum(
            1 for slot in (p.city, p.street, p.house, p.apartment, p.account_code) if slot.value
        )
        s = self.state
        return (
            s.customer_id,
            filled,
            s.problem_type,
            s.outage_reported,
            s.case_closed,
            s.ticket_id,
        )

    @staticmethod
    def _is_question(text: str) -> bool:
        return text.strip().endswith("?")

    def _sanitize_question(self, text: str) -> str:
        """Lowercase, drop punctuation + politeness fillers, collapse whitespace —
        so two questions compare on their CORE, not their wording trim."""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
        return " ".join(w for w in cleaned.split() if w not in _STUCK_FILLER)

    def _similar(self, a: str, b: str) -> bool:
        """True if two questions are effectively the same re-ask (containment, to
        catch an added prefix, or a high difflib ratio on the sanitized cores)."""
        from difflib import SequenceMatcher

        sa, sb = self._sanitize_question(a), self._sanitize_question(b)
        if not sa or not sb:
            return False
        if sa in sb or sb in sa:
            return True
        return SequenceMatcher(None, sa, sb).ratio() > 0.8

    def _stuck_backstop(self) -> tuple[str, bool] | None:
        """Deterministic escalation (text, should_close) once the prompt-level nudge
        has failed — fired BEFORE the LLM (so it works with token streaming): at 3
        offer the account code, at 4 register + close. None below that."""
        n = self.state.stuck_count
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
        progressed = self._progress_key() != self._turn_start_key
        is_q = self._is_question(reply)
        repeat = bool(
            is_q and self.state.last_question and self._similar(reply, self.state.last_question)
        )
        self._repeated_verbatim = repeat
        if progressed:
            self.state.stuck_count = 0
        elif repeat:
            self.state.stuck_count += 1
        # else: a different question or a statement leaves the counter unchanged —
        # only a real re-ask escalates, and only real progress clears it.
        if is_q:
            self.state.last_question = reply
        self.tracer.emit("stuck", count=self.state.stuck_count, repeated=repeat)

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
        if self._is_question(text):
            self.state.last_question = text
        self._emit_case()
        self.tracer.emit("scripted", where="identification")
        self.tracer.emit("agent_reply", text=text)
        return text

    def _apply_backstop(self, backstop: tuple[str, bool]) -> str:
        """Emit a deterministic backstop reply (manages the counter itself so a
        repeat backstop climbs 3 -> 4 -> close). Returns the text to yield/return."""
        text, should_close = backstop
        if should_close:
            self.state.case_closed = True
            self.state.closed_reason = "declined"
        else:
            self.state.stuck_count += 1  # advance the ladder for the next turn
        self.state.messages.append({"role": "assistant", "content": text})
        if self._is_question(text):
            self.state.last_question = text
        self._maybe_end_on_goodbye(text)
        self._emit_case()
        self.tracer.emit("stuck", count=self.state.stuck_count, repeated=False)
        self.tracer.emit("agent_reply", text=text)
        return text

    def _maybe_raise_clarity(self, user_input: str | None) -> None:
        """Once the caller says they do not follow the wording ("kas tas WAN?"),
        stay in plain language for the rest of the call. One-way: a caller who was
        lost once should not be dropped back into jargon two steps later."""
        from .resolution import detect_confusion

        if self.state.clarity_level == "standard" and detect_confusion(user_input):
            self.state.clarity_level = "basic"

    def _maybe_end_on_goodbye(self, text: str) -> None:
        """Delegates to closing_flow.maybe_end_on_goodbye (R3 extraction)."""
        from .closing_flow import maybe_end_on_goodbye

        maybe_end_on_goodbye(self, text)

    def _finalize_reply(self, text: str) -> None:
        """Shared end-of-turn bookkeeping for a customer-facing reply: update the
        repeat-guard, emit the case snapshot + the reply trace."""
        self._track_stuck(text)
        self._maybe_end_on_goodbye(text)
        self._emit_case()
        self.tracer.emit("agent_reply", text=text)

    def _emit_case(self) -> None:
        """Emit a compact case-state snapshot to the TRACE (for review) — NOT into
        the LLM context. The lean current-truth the model reads is the facts block;
        the full running summary / history stays in the trace + DB (§12.7)."""
        s = self.state
        diag = (
            "; ".join(f"{dom}:{f.get('group')}/{f.get('reason')}" for dom, f in s.diagnosis.items())
            or None
        )
        if not (s.problem_type or s.customer_id or diag or s.symptoms):
            return
        r = s.resolution or {}
        h = s.hypothesis or {}
        self.tracer.emit(
            "case",
            problem=s.problem_type,
            customer_id=s.customer_id,
            address=s.customer_address,
            symptoms=(", ".join(f"{k}={v}" for k, v in s.symptoms.items()) or None),
            diagnosis=diag,
            # Decision state — the "where are we / why" that a raw reply hides.
            step=r.get("step"),
            awaiting=s.awaiting,
            clarity=s.clarity_level if s.clarity_level != "standard" else None,
            hypothesis=(f"{h.get('cause')}:{h.get('status')}" if h else None),
        )

    def _trace_note(self, where: str, detail: str, level: str = "warn") -> None:
        """Record a behaviour-affecting failure/fallback INTO the trace (not only the
        console log), stamped with the current state (node/step/awaiting), so a call
        review shows WHY the agent behaved as it did — a swallowed classifier/solver/tool
        error no longer disappears from the JSONL. Best-effort; never raises."""
        try:
            r = self.state.resolution or {}
            self.tracer.emit(
                "error",
                level=level,
                where=where,
                detail=(detail or "")[:300],
                node=self._active_node,
                step=r.get("step"),
                awaiting=self.state.awaiting,
            )
        except Exception:  # pragma: no cover - tracing must never break the turn
            pass

    def _reply(self, text: str) -> str:
        """Emit the customer-facing reply (with repeat-guard bookkeeping) and return it."""
        self._finalize_reply(text)
        return text


# =============================================================================
# CLI INTERFACE
# =============================================================================


def run_cli(caller_phone: str = "+37060012345", language: str = "lt"):
    """Run interactive agent session in CLI."""
    # Local import avoids a circular import (session imports ReactAgent).
    from .session import AgentSession

    print("\n" + "=" * 60)
    print("ISP SUPPORT AGENT (ReAct)")
    print("=" * 60)
    print(f"Caller phone: {caller_phone}")
    print(f"Language: {language}")
    print("Type 'quit' to exit, 'debug' to toggle debug mode")
    print("=" * 60 + "\n")

    # Drive the CLI through the stable AgentSession boundary (same seam voice
    # and web use), not the ReactAgent engine directly.
    session = AgentSession(caller_phone=caller_phone, language=language)
    debug_mode = False

    # Initial greeting
    initial_response = session.greeting()
    if initial_response:
        print(f"\n🤖 Agent: {initial_response}\n")

    while not session.is_complete:
        try:
            user_input = input("👤 You: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print(f"\n{session.config.cli_goodbye_message}")
                break

            if user_input.lower() == "debug":
                debug_mode = not debug_mode
                logging.getLogger().setLevel(logging.DEBUG if debug_mode else logging.INFO)
                print(f"[Debug mode: {'ON' if debug_mode else 'OFF'}]")
                continue

            if user_input.lower() == "state":
                print(f"\n[STATE] {session.state.to_dict()}\n")
                continue

            response = session.handle_turn(user_input)
            print(f"\n🤖 Agent: {response}\n")

        except KeyboardInterrupt:
            print(f"\n\n{session.config.cli_interrupted_message}")
            break

    # Close the trace for this conversation (emits session_end).
    session.end_session(outcome="cli_quit")

    print("\n" + "=" * 60)
    print(f"Conversation ended. Turns: {session.state.turn_count}")
    if session.state.customer_id:
        print(f"Customer: {session.state.customer_name} ({session.state.customer_id})")
    if session.state.ticket_id:
        print(f"Ticket: {session.state.ticket_id}")
    print(f"Trace: logs/sessions/{session.session_id}.jsonl")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ISP Support Agent CLI")
    parser.add_argument("--phone", default="+37060012345", help="Caller phone number")
    parser.add_argument("--lang", default="lt", choices=["lt", "en"], help="Language (lt or en)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Mask phone numbers in logs (after basicConfig set up the root handler).
    from utils import install_pii_redaction

    install_pii_redaction()

    run_cli(caller_phone=args.phone, language=args.lang)
