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
import os
import re
import time
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

# When the agent's reply contains one of these, the call is over — end it (hang up)
# no matter which path produced the goodbye. Kept to clear terminal farewells so a
# mid-conversation "gero" never trips it.
_GOODBYE_MARKERS = (
    "geros dienos",
    "geros jums dienos",
    "gražios dienos",
    "gero vakaro",
    "gražaus vakaro",
    "viso gero",
    "viso labo",
)


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

# Short Lithuanian gloss for each verdict reason, surfaced in the case-state facts
# block so the agent can reconcile the finding with what the customer says.
_DIAGNOSIS_LT = {
    "billing_suspended": "paslauga sustabdyta dėl neapmokėtos sąskaitos",
    # Worded WITHOUT "registruota" — the outage eval guard forbids "registr" (its
    # intent: no TICKET talk for outages) and the scripted news must not trip it.
    "active_outage": "rajone šiuo metu vyksta masinė avarija",
    "switch_unreachable": "tinklo mazgas nepasiekiamas (tiekėjo gedimas)",
    "node_fault_unregistered": "mazgo gedimas (neregistruotas)",
    "link_down_local": "ryšys iki kliento įrangos nutrūkęs (maitinimas/laidas)",
    "foreign_mac": "linijoje matomas kitas įrenginys (MAC) nei registruota",
    "crc_errors": "linijos klaidos (CRC) — kabelio/jungties problema",
    "dhcp_silent": "įranga negauna IP (DHCP tyli) — galbūt po gamyklinio atstatymo",
    "no_mac_observed": "linijoje nematoma jokio įrenginio",
    "healthy_to_router": "tinklas iki routerio veikia — problema kliento pusėje",
    "no_port_data": "nėra prievado duomenų",
}

# WHY the ticket is needed, in the caller's words — spoken in the dialogue intro
# ("Registruoju gedimą — reikalingas naujas maršrutizatorius.") and written on the
# ticket. Falls back to the _DIAGNOSIS_LT gloss for causes without a need phrase.
_TICKET_NEED_LT = {
    "no_mac_observed": "reikalingas naujas maršrutizatorius",
    "link_down_local": "reikia patikrinti liniją iki jūsų buto",
}

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
        # Ticket-confirmation dialogue (2026-08-04): every registration first collects
        # the contact number (ALWAYS asked, never assumed) and when to call. Stage is
        # None | "phone" | "hours" | "done"; ctx remembers the escalate step to build
        # the ticket from once the dialogue completes.
        self._ticket_stage: str | None = None
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

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

    def _build_messages(self, user_input: str = None) -> list:
        """
        Build the message payload for one LLM call.

        Token cost grows with conversation length because the whole history is
        resent every turn. To keep voice latency and cost bounded we send only
        a recent *window* of history (see _prune_history) plus a compact block
        of durable facts re-injected from AgentState (see _state_facts_block),
        so pruning old messages never loses the resolved customer/problem/ticket
        context. The full transcript still lives in AgentState.messages.

        Prompt-cache friendliness: the system prompt is kept BYTE-STABLE across
        turns so providers can cache the prefix. The durable-fact block changes
        as the call progresses, so it goes in a SEPARATE trailing system message
        (just before the new user input) rather than being concatenated into the
        system content — concatenating would mutate the system message every turn
        and bust the cache (the real cost, not the few fact tokens).
        """
        # Stable system prefix (cacheable).
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add recent conversation history (windowed, tool-pairing safe)
        messages.extend(self._prune_history(self.state.messages))

        # Durable facts as a trailing system message (kept OUT of the cached
        # prefix). None until something is resolved this call.
        facts = self._state_facts_block()
        if facts:
            messages.append({"role": "system", "content": facts})

        # Per-node focus prompt (graph stage), if a node set one.
        if self._node_prompt:
            messages.append({"role": "system", "content": self._node_prompt})

        # Add new user input if provided
        if user_input:
            messages.append({"role": "user", "content": user_input})

        # Debug: what the LLM actually SEES this turn — the dynamic facts block is
        # where "why did it say that" lives. Off by default (would bloat the trace);
        # DEBUG_LLM=1 turns it on. The stable system prompt is omitted (it never
        # changes); full messages only when DEBUG_LLM=full.
        if os.environ.get("DEBUG_LLM"):
            payload: dict[str, Any] = {
                "node": self._active_node,
                "facts": facts,
                "tools": sorted(t["function"]["name"] for t in self._scoped_tools_schema()),
                "history_msgs": len(messages) - 1,
            }
            if os.environ.get("DEBUG_LLM") == "full":
                payload["messages"] = messages
            self.tracer.emit("llm_input", **payload)

        return messages

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
        """The tool schema for the current node — all tools, or the subset a graph
        node restricted the model to (self._active_tool_names).

        Per-step scoping while a resolution strategy is active: the engine owns all
        diagnostics (withheld); an ACTION/ESCALATE step exposes ONLY its tool so the
        model does that action once; a CONFIRM step (or a case being closed) exposes
        NO action tool. This prevents both 'binds before confirm' and the tool-call
        loop where the model re-calls the one exposed tool until the 5-call limit."""
        # Case closed mid-turn (bind resolved / ticket registered): no tools at all,
        # so the model narrates the close instead of looping tool calls to the limit
        # (which surfaced the 'negaliu apdoroti' fallback).
        if self.state.case_closed:
            return []
        schema = self.tools_schema
        if self._active_tool_names is not None:
            schema = [
                t for t in schema if t.get("function", {}).get("name") in self._active_tool_names
            ]
        if self.state.resolution is not None:
            from .resolution import StepKind, get_strategy

            strat = get_strategy(self.state.resolution.get("verdict"))
            step = strat.step(self.state.resolution.get("step", "")) if strat else None
            if step is not None:
                # Scope to EXACTLY this step's tools. A CONFIRM / INSTRUCT / VERIFY
                # step has NONE — the model just talks while the engine owns the
                # diagnostics, the action and the closing. This is what stops the
                # model spamming an unrelated lookup while it "waits" (observed:
                # check_outages looped to the call limit -> 'negaliu apdoroti').
                allowed = step.tools
                # An ACTION step exposes its tool ONLY as a fallback if the engine
                # has not already run it. Once action_done is set, WITHHOLD it — the
                # model only announces; otherwise the single exposed tool gets
                # re-called to the limit (observed: update_mac x6 -> 'negaliu apdoroti').
                if step.kind == StepKind.ACTION and self.state.resolution.get("action_done"):
                    allowed = frozenset()
                schema = [t for t in schema if t.get("function", {}).get("name") in allowed]
            else:
                schema = [
                    t
                    for t in schema
                    if (n := t.get("function", {}).get("name")) not in self._STRATEGY_DIAG_TOOLS
                    and n not in self._STRATEGY_ACTION_TOOLS
                ]
        return schema

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
        """
        Return the most recent slice of history that fits the configured window.

        Pairing safety: native tool calling requires every role:"tool" message to
        be preceded by the assistant message that issued the matching tool_calls.
        A naive "last N" cut can land mid-exchange and orphan a tool result, which
        the chat API rejects (400). So if the window would start on a tool result,
        we walk the start index left until it lands on the owning assistant
        message, keeping the exchange intact.
        """
        window = self.config.history_window_messages
        if window <= 0 or len(messages) <= window:
            return list(messages)

        start = len(messages) - window
        while start > 0 and messages[start].get("role") == "tool":
            start -= 1
        return messages[start:]

    def _state_facts_block(self) -> str | None:
        """
        Render durable facts from AgentState as a short system addendum.

        These survive history pruning (they live in AgentState, not the message
        log), so re-injecting them keeps the model from re-asking for details it
        already resolved. Returns None when nothing has been resolved yet.
        """
        s = self.state
        facts: list[str] = []
        # Ticket-dialogue off-script turn: the caller asked something instead of
        # answering the stage question — give the LLM the answers it may need and
        # the EXACT question to re-ask. Leads the block; nothing else competes.
        if self._ticket_stage in ("phone", "hours"):
            from .identification import phrase

            pending = (
                phrase("ticket_phone") if self._ticket_stage == "phone" else phrase("ticket_hours")
            )
            facts.append(
                "- TIKETO DIALOGAS: registruojame gedimą (priežastis: "
                f"{self._ticket_need()}). Skambinančiojo numeris: "
                f"{self._fmt_phone(s.caller_phone) or 'nežinomas'}. Tiketas DAR "
                "neužregistruotas — nesakyk „užregistravau“. Atsakyk į kliento "
                f"klausimą VIENU sakiniu ir būtinai pakartok klausimą: „{pending}“"
            )
        # Per-turn guards (deterministic, set in _pre_turn_guards) lead the block —
        # they override the model's own reading of the last reply.
        if getattr(self, "_addr_confirm_note", None):
            facts.append(self._addr_confirm_note)
        if getattr(self, "_reopen_note", False) and not s.customer_id:
            facts.append(
                "- KLIENTAS PATIKSLINO: skambina dėl KITO adreso nei buvo nustatyta. "
                "Atsiprašyk vienu sakiniu ir paprašyk pasakyti adresą, dėl kurio "
                "skambina (jei jau pasakė — žr. HEARD ADDRESS ir naudok jį). Ankstesnio "
                "adreso ir jo diagnozės NEBEminėk."
            )
        # Proactive mass-outage (the ONE time the phone is used up front): if the
        # caller's street has an active outage, inform immediately instead of
        # identifying. Leads the block so it drives the FIRST reply. Reveals only
        # the street, and as a question — not an identity claim.
        if s.preflight_outage and not s.customer_id and not s.case_closed:
            o = s.preflight_outage
            eta = f", atstatymas iki {o['eta']}" if o.get("eta") else ""
            facts.append(
                f"- PROACTIVE OUTAGE: the caller's number is registered on {o['street']}, "
                f"which has an ACTIVE mass outage{eta}. The caller has NOT named this "
                f"street — do NOT say 'Girdžiu {o['street']}' or claim they mentioned it. "
                f"Ask NEUTRALLY and WAIT for their answer: 'Ar skambinate dėl "
                f"{o['street']}?'. ONLY after they confirm, inform about the outage + "
                f"estimated time and then call close_case(reason='outage'). Do NOT run "
                f"identification (no 'Radau sutartį', no house/apartment). If they name a "
                f"DIFFERENT street, drop this and ask for the address."
            )

        # Phone account: the caller's number is in the DB. Offer its registered
        # address FIRST (before asking them to dictate anything) — the number is
        # already tied to that address, so it reveals nothing new and saves the
        # STT-fragile spoken house/apartment. Fires until they name a DIFFERENT
        # street (then they are calling about someone else's address — case B).
        # Every named part must match (or be unsaid): if the caller gives the same
        # street but a DIFFERENT flat ("Tilžės 60, butas 3"), this is someone else's
        # address — stop offering, or the model reuses the phone's parts and resolves
        # the WRONG customer (observed: said butas 3, resolved butas 7).
        def _fits(said, mine) -> bool:
            return not said or str(said).lower() == str(mine or "").lower()

        from .identification import extra_questions_guidance, offer_phone_address

        if (
            offer_phone_address()
            and not s.customer_id
            and not s.preflight_outage
            and s.phone_candidate
            and s.phone_candidate.get("street")
            and _fits(s.profile.street.value, s.phone_candidate.get("street"))
            and _fits(s.profile.house.value, s.phone_candidate.get("house"))
            and _fits(s.profile.apartment.value, s.phone_candidate.get("apartment"))
        ):
            c = s.phone_candidate
            flat = f", butas {c['apartment']}" if c.get("apartment") else ""
            flat_arg = f", apartment_number='{c['apartment']}'" if c.get("apartment") else ""
            facts.append(
                f"- PHONE ACCOUNT: the caller's number is registered at {c['address']}. "
                f"Offer THIS address FIRST, before asking them to dictate anything: "
                f'"Ar skambinate dėl {c["street"]} {c["house"]}{flat}?". On yes, call '
                f"resolve_address(city='{c['city']}', street='{c['street']}', "
                f"house_number='{c['house']}'{flat_arg}) to identify, then diagnose. If they "
                f"say a DIFFERENT address (someone else's — that is allowed), ask them to "
                f"state the address where the fault is and take THAT."
            )
        # DB-grounded verdict on the accumulated address (set in the prefill).
        if self._db_address_note and not s.customer_id:
            facts.append(self._db_address_note)
        # Extra verification questions declared in identification.yaml (e.g. the name),
        # asked while still identifying. Empty by default → nothing added.
        if not s.customer_id:
            extra = extra_questions_guidance()
            if extra:
                facts.append(extra)
        if s.customer_id:
            facts.append(f"- Customer ID: {s.customer_id}")
        if s.customer_name:
            facts.append(f"- Customer name: {s.customer_name}")
        if s.customer_address:
            facts.append(f"- Address: {s.customer_address}")
        if s.problem_type:
            facts.append(f"- Problem type: {s.problem_type}")
        if s.symptoms:
            parts = ", ".join(f"{k}={v}" for k, v in s.symptoms.items())
            facts.append(
                f"- SYMPTOMAI (kliento): {parts}. Naudok diagnozei ir klausk tik "
                "TRŪKSTAMŲ; nepersiklausk to, ką jau žinai."
            )
        if s.ticket_id:
            facts.append(f"- Ticket: {s.ticket_id}")
        if s.case_closed and s.is_complete:
            # The caller said goodbye / "no more" — END on ONE short farewell.
            facts.append(
                "- POKALBIS BAIGTAS: klientas atsisveikino / neturi daugiau klausimų. "
                "Pasakyk TIK vieną trumpą atsisveikinimą („Ačiū, kad paskambinote. "
                "Geros dienos!“) ir NIEKO daugiau — jokių naujų klausimų."
            )
        elif s.case_closed:
            facts.append(f"- Byla UŽDARYTA (priežastis: {s.closed_reason or 'resolved'}).")
            # Engine-registered ticket (consent-free ESCALATE): the narrator ANNOUNCES
            # the registration — it must not ask permission or offer to register again.
            if s.closed_reason == "registered" and s.ticket_id:
                facts.append(
                    "- UŽREGISTRUOTA: gedimas jau užregistruotas (variklis tai padarė). "
                    "Pasakyk vienu sakiniu: užregistravau gedimą, kolegos susisieks ir "
                    "detaliau paaiškins. NEklausk sutikimo, NEsiūlyk registruoti dar "
                    "kartą, neskaityk ticket ID."
                )
            # Just resolved: confirm briefly, then OFFER one more thing and WAIT — do
            # NOT sign off yet (the engine ends the call once the caller declines).
            if s.closed_reason == "resolved" and s.resolution:
                facts.append(
                    "- IŠSPRĘSTA: klientas patvirtino, kad internetas veikia. Trumpai "
                    "padžiaukis, kad sutvarkyta, ir paklausk „Ar dar kuo nors galiu "
                    "padėti?“. NEatsisveikink dar, NEklausk apie įrangą, NEprašyk "
                    "tikrinti iš naujo."
                )
        # Repeat-guard nudge (scaled): the caller's last reply did not advance us.
        # Don't loop the same question — acknowledge, narrow, then change tactic.
        # The account-code tactic belongs to IDENTIFICATION only — once the customer is
        # known it leaked into late-call narration ("Gal turite abonento kodą?" right
        # after registering a ticket, observed live).
        if s.stuck_count >= 2 and not s.customer_id:
            facts.append(
                "- STRIGTI: to paties klausimo NEBEKARTOK. Pakeisk taktiką — pasiūlyk "
                "abonento kodą („Gal turite abonento kodą nuo sąskaitos?“) arba "
                "užregistruok problemą atskambinimui."
            )
        elif s.stuck_count >= 2:
            facts.append(
                "- STRIGTI: to paties klausimo NEBEKARTOK. Perfrazuok kitaip arba "
                "pasiūlyk užregistruoti gedimą (technikas susisieks). NEklausk abonento "
                "kodo — klientas jau identifikuotas."
            )
        elif s.stuck_count == 1:
            extra = (
                " Praeitą klausimą uždavei pažodžiui — BŪTINAI perfrazuok."
                if self._repeated_verbatim
                else ""
            )
            if s.last_heard:
                # We DID hear them — we just could not use it. Never say "neišgirdau"
                # here: reflect the actual words and name the part that is unclear, so
                # the caller knows they were heard and what exactly to repeat.
                facts.append(
                    f"- NESUPRATAU (girdėjau!): klientas ką tik pasakė „{s.last_heard}“, bet "
                    "iš to nepavyko paimti, ko reikia. NESAKYK „neišgirdau“ — pasakyk, ką "
                    "girdėjai ir ko NEsupratai, ir paprašyk pakartoti TIK tą dalį: "
                    "„Girdžiu „…“, bet nesupratau gatvės — pakartokite ją, prašau.“ Jei "
                    "klientas iš tikrųjų kalba APIE KĄ KITA (klausia ko nors, tikslinasi) — "
                    "atsakyk į TAI, o ne kartok savo klausimą." + extra
                )
            else:
                # Silence. The caller may just be listening or thinking, so do NOT
                # apologise at them — "neišgirdau" after they said nothing reads as if
                # THEY failed. Leave the pause; simply ask for what is needed.
                facts.append(
                    "- TYLA (klientas nieko nepasakė): NESAKYK „neišgirdau“ — jis gali "
                    "tiesiog klausytis ar galvoti. Ramiai, be atsiprašinėjimo, paklausk "
                    "to, ko reikia (pvz. gatvės), arba pasitikslink „Ar mane girdite?“. "
                    "Neskubėk." + extra
                )
        # Raw-buffer reconciliation: once we're stuck AND still unidentified, hand
        # the LLM EVERYTHING the caller said so far. VAD/STT splits and garbles
        # spoken numbers ("šešiasdešimt" -> "šešias dešimt" -> a fragment that
        # parses as 10, not 60); no single turn resolves, but the whole buffer
        # lets the model infer the intended address. Only kicks in when the
        # deterministic path has stalled, so the clean case stays LLM-free.
        if not s.customer_id and s.stuck_count >= 1 and len(s.heard_utterances) >= 2:
            recent = " | ".join(s.heard_utterances[-8:])
            facts.append(
                "- ALL HEARD (reconcile): the caller has said these pieces so far: "
                f'"{recent}". STT may have split or garbled a spoken number '
                '("šešiasdešimt" 60 can arrive as "šešias dešimt" and mis-parse to 10). '
                "Infer the MOST LIKELY full address from everything above (prefer the "
                "latest correction), then call resolve_address with it — do not make the "
                "caller repeat again if you can reasonably infer it."
            )
        # Outage reported (restricted mode): an active outage IS the answer, so stop
        # identifying/diagnosing — but stay available for the caller's follow-ups
        # (ETA, compensation) and close only when they are done (close_case).
        if s.outage_reported and not s.case_closed:
            facts.append(
                "- GEDIMAS PASKELBTAS šiai gatvei — tai galutinis atsakymas. NEklausk "
                "namo/buto, NEdiagnozuok, NEsiūlyk maitinimo/laidų. Atsakyk į kliento "
                "klausimus apie gedimą (laikas, eiga, kompensacija; gali naudoti "
                "search_knowledge). Kai klientas supranta / lauks — kviesk "
                "close_case(reason='outage')."
            )
        # Diagnostic findings (case state), per domain: durable current truth, so
        # the agent reconciles them with the caller and never re-runs / loses them.
        # Only active domains are surfaced (lean — history lives in the trace, §12.7).
        # BUT once the strategy has run the action (telemetry_fixed recorded), the
        # raw finding is STALE — surfacing "foreign_mac: kitas įrenginys" post-bind
        # made the agent re-narrate the solved problem ("dar nepririštas") every
        # turn. Past the bind, the step's own hint is the single source of truth.
        past_action = bool(s.resolution) and "telemetry_fixed" in (s.resolution or {})
        # Identification ladder's last rung: the caller-intro question is OWED (asked
        # this reply) — the deferred check result comes next turn, so the finding facts
        # are suppressed to keep the model from blurting it alongside the question.
        caller_pending = bool(s.customer_id) and self._result_pending and not s.caller_name
        if caller_pending:
            from .identification import caller_question

            facts.append(
                "- IDENTIFIKACIJOS PABAIGA: patikra atlikta, bet rezultato dar "
                f"NESAKYK. Šiame atsakyme TIK klausimas: „{caller_question()}“. "
                "Jokio rezultato, jokių instrukcijų."
            )
        elif s.customer_id and self._result_pending and s.caller_name:
            # The caller introduced themselves — deliver the deferred result NOW.
            facts.append("- REZULTATO PRISTATYMAS:" + self._result_narration_tail())
        if not past_action and not caller_pending:
            for domain, d in s.diagnosis.items():
                gloss = _DIAGNOSIS_LT.get(d.get("reason"), d.get("reason") or "—")
                facts.append(
                    f"- DIAGNOSTIKA [{domain}] ({d.get('group')}, pusė={d.get('side')}): "
                    f"{gloss}. Remkis šiais radiniais; NEdiagnozuok iš naujo ir jų "
                    "neprarask. Jei klientas sako kitaip nei rodo diagnostika, švelniai "
                    "sutaikink."
                )
        # What we believe and why — so the agent reasons out loud instead of issuing
        # orders, and can CONFIRM the cause at the end ("taigi dėl X ir nebuvo").
        h = None if caller_pending else s.hypothesis
        if h:
            because = "; ".join(h["because"])
            if h["status"] == "confirmed":
                facts.append(
                    f"- HIPOTEZĖ PASITVIRTINO: „{_DIAGNOSIS_LT.get(h['cause'], h['cause'])}“ "
                    f"({h['settled_by']}). Trumpai pasakyk klientui, kad būtent dėl to ir "
                    "neveikė — jam svarbu suprasti, kas buvo."
                )
            elif h["status"] == "testing":
                facts.append(
                    f"- KO DABAR IEŠKAU: „{_DIAGNOSIS_LT.get(h['cause'], h['cause'])}“. "
                    f"Kuo remiuosi: {because}. Kai tinka, pasakyk tai savais žodžiais "
                    "(„matau X, todėl manau, kad Y“) — bet trumpai ir ne kas ėjimą."
                )
        if s.rejected_hypotheses and not s.case_closed:
            ruled = ", ".join(
                _DIAGNOSIS_LT.get(x["cause"], x["cause"]) for x in s.rejected_hypotheses
            )
            facts.append(f"- JAU ATMESTA (nebesiūlyk ir nebetikrink): {ruled}.")
        # The turn did not move the conversation on. Say WHY, so the agent responds to
        # what the caller actually did instead of re-asking the same sentence.
        if s.awaiting and not s.case_closed:
            from .resolution import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

            if s.last_intent == INTENT_IN_PROGRESS:
                facts.append(
                    "- KLIENTAS DAR DARO: jis sakė, kad tuoj/eina/atsineš — dar NEatliko. "
                    "Trumpai patvirtink, kad palauksi („Gerai, palauksiu — pasakykite, "
                    "kai būsite pasiruošęs“) ir LAUK. NEkartok instrukcijos, NEtark, kad "
                    "nepavyko, ir NEeik toliau."
                )
            elif s.last_intent == INTENT_QUESTION:
                facts.append(
                    "- KLIENTAS PAKLAUSĖ: pirma ATSAKYK į jo klausimą paprastai, tada "
                    "švelniai grįžk prie to, ko prašei. Nekartok savo klausimo neatsakęs."
                )
            elif s.last_intent == INTENT_CONFUSED:
                if s.step_confusions >= 2:
                    facts.append(
                        "- VIS DAR NESUPRANTA (jau 2+ kartus): nustok aiškinti tą patį. "
                        "Paimk MAŽIAUSIĄ įmanomą dalį — vieną fizinį veiksmą, kurį "
                        "galima padaryti per sekundę („Ar matote dėžutę su lemputėmis? "
                        "Tiesiog pasakykite taip ar ne“) — ir eik po vieną tokį. Jei ir "
                        "tai nepavyksta, pasiūlyk užregistruoti, kad atvyktų technikas."
                    )
                else:
                    facts.append(
                        "- KLIENTAS NESUPRATO: NEkartok tų pačių žodžių. Suskaidyk šį "
                        "žingsnį į MAŽESNĮ — pirma nuvesk, KUR pažiūrėti ir kaip tai "
                        "atrodo, ir paprašyk tik to vieno dalyko."
                    )
            if s.awaiting_turns >= 3:
                facts.append(
                    "- ILGAI LAUKIAM: praėjo keli ėjimai be pastūmėjimo. Pasitikslink "
                    "žmogiškai, kaip sekasi ir kur jis dabar („Ar pavyksta rasti? Gal "
                    "pasakykite, ką matote“), arba pasiūlyk registruoti gedimą."
                )
        # The caller told us they do not follow the jargon — repeating the same words
        # louder does not help. Give the model plain, visual equivalents to use.
        if s.clarity_level == "basic" and not s.case_closed:
            facts.append(
                "- PAPRASTAI: klientas sakė, kad nesupranta techninių žodžių. Kalbėk "
                "VAIZDŽIAI, be žargono, po VIENĄ veiksmą. Vietoj terminų sakyk: "
                "routeris = „dėžutė su lemputėmis“; WAN/interneto lizdas = „lizdas, į "
                "kurį įkištas kabelis, ateinantis iš sienos, dažnai atskiras ir "
                "pažymėtas Internet“; LAN = „kiti lizdai šalia, į kuriuos jungiami "
                "namų įrenginiai“; MAC = „įrenginio numeris mūsų sistemoje“. Nurodyk, "
                "KUR pažiūrėti („routerio galinėje pusėje“), o ne tik KĄ."
            )
        # Just rejected a hypothesis and switched: let the caller HEAR the rethink, so
        # a failed first attempt reads as an engineer working the problem (we have a
        # Plan B) rather than a script that silently restarts.
        if s.pivoted_from and not s.case_closed:
            old = _DIAGNOSIS_LT.get(s.pivoted_from, s.pivoted_from)
            facts.append(
                f"- PERSIGALVOJIMAS: bandėme priežastį „{old}“ ir tai NEPADĖJO "
                "(telemetrija). Pradėk atsakymą tuo, žmogiškai ir trumpai: kad tai "
                "nepadėjo, vadinasi priežastis kita, ir ką dabar tikrini. Tada tęsk "
                "pagal ŠĮ ŽINGSNĮ. NEapsimesk, kad ankstesnio bandymo nebuvo, ir "
                "NEkartok jo."
            )
        # INFORM (no strategy — billing/outage): the news went out in the activation
        # reply (arc v3). The JAU PRANEŠTA marker stops the model re-reading the same
        # news every turn (observed live: "sustabdyta dėl skolos" said 3×).
        if s.resolution is None and s.diagnosis and not s.case_closed:
            if getattr(self, "_news_told", False):
                facts.append(
                    "- ŽINIA JAU PASAKYTA: nebekartok „patikrinau / sustabdyta / "
                    "avarija“ teksto. Atsakyk į kliento klausimą, arba paklausk „Ar dar "
                    "kuo galiu padėti?“ ir užbaik pokalbį."
                )
        # Active resolution strategy: inject ONLY the current step's playbook
        # section (never the whole doc — a streaming model would run several steps
        # ahead). This is the "what to do NOW" for the step the engine is on.
        if s.resolution and not s.case_closed:
            from .playbook import get_step
            from .resolution import get_strategy

            strat = get_strategy(s.resolution.get("verdict"))
            step = strat.step(s.resolution.get("step", "")) if strat else None
            # Step facts wait while the caller-intro question is owed (see above).
            if step is not None and not caller_pending:
                if step.rag_section is not None:
                    section = get_step(strat.rag_doc, step.rag_section)
                    if section:
                        # Observability: WHICH knowledge chunk feeds THIS step (the
                        # trace otherwise never shows the RAG injection — only
                        # DEBUG_LLM did, with far too much noise).
                        self._emit_rag_injection(strat.rag_doc, step.rag_section, step.id, section)
                        facts.append(
                            "- PLAYBOOK — your INTERNAL guidance for THIS step (Lithuanian "
                            "content). Act on it, do NOT read it to the caller verbatim, "
                            "ask ONE thing at a time. Say ONLY what THIS step is about — "
                            "do NOT invent instructions it does not mention (no rebooting, "
                            "no lights, no cables unless this step says so). If the caller's "
                            "answer was unclear, ask THIS SAME thing again in other words:\n"
                            + section
                        )
                if step.hint:
                    facts.append(f"- THIS STEP: {step.hint}")
        # Deterministically heard address parts (NLU Track A prefill). Surface them
        # so the model passes THESE to resolve_address instead of re-extracting
        # garbled STT (observed: NLU heard "Aušros g. 8" but the model sent
        # "Raušuos"). Only relevant before the customer is identified.
        if not s.customer_id:
            p = s.profile
            heard = [
                f"{label}={slot.value}"
                for label, slot in (
                    ("city", p.city),
                    ("street", p.street),
                    ("house", p.house),
                    ("apartment", p.apartment),
                )
                if slot.value
            ]
            if heard:
                facts.append(
                    "- HEARD ADDRESS (deterministic — PREFER these over re-extracting "
                    "from the raw text): " + ", ".join(heard) + ". Pass them to "
                    "resolve_address unless the caller explicitly corrects them."
                )
        # Phone candidate is NOT surfaced to the model. Identification is
        # address-first: the agent always asks for the service address and
        # resolve_address is what commits the customer_id. The preflight
        # phone_candidate stays in AgentState for SILENT use only — a
        # deterministic cross-check (does the stated address match the caller's
        # account?) and the mass-outage fast-path — never as an address to
        # offer. Surfacing it caused the model to (a) re-ask the same
        # confirmation without ever committing the id, and (b) present a
        # user-stated address as "skambinate iš numerio, registruoto adresu ..."
        # even for callers with no account on file.

        # Evidence ledger — the narrator's grounding: settled facts are never
        # re-asked, and nothing outside the ledger may be claimed as checked.
        if s.evidence and s.customer_id and not s.case_closed:
            from .evidence import summary_lt

            facts.append(
                "- ĮRODYMŲ ŽURNALAS (nustatyta šį pokalbį — NEBEKLAUSK ir "
                f"neprieštarauk): {summary_lt(s.evidence)}"
            )

        if not facts:
            return None

        return "KNOWN FACTS (already resolved this call — do not ask again):\n" + "\n".join(facts)

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
        """Re-read telemetry now and return the verdict reason (or None on error).
        Read-only — used to VERIFY a fix actually took before closing/acting."""
        if not self.state.customer_id:
            return None
        try:
            d = json.loads(
                execute_tool("diagnose_connection", {"customer_id": self.state.customer_id})
            )
            return (d.get("verdict") or {}).get("reason")
        except Exception:  # pragma: no cover - best-effort
            return None

    def ensure_diagnosed(self) -> bool:
        """Deterministically run diagnose_connection the first time we enter the
        diagnosis stage (customer identified), so the verdict + strategy are set
        BEFORE the model narrates. The flow no longer depends on the model choosing
        to diagnose — which it did inconsistently (sometimes jumping straight to
        update_mac, sometimes re-diagnosing into another branch).

        Returns True if it ran diagnose on THIS call (first entry), so the caller
        skips a step advance that turn — the strategy's first question is only being
        asked now, not yet answered."""
        s = self.state
        if not s.customer_id or s.case_closed:
            return False
        if s.diagnosis.get("network") or s.outage_reported:
            return False  # already diagnosed this stage (or an outage short-circuited it)
        try:
            obs = execute_tool("diagnose_connection", {"customer_id": s.customer_id})
        except Exception:  # pragma: no cover - best-effort
            return False
        self.tracer.emit(
            "tool_call", name="diagnose_connection", args={"customer_id": s.customer_id}
        )
        self._trace_tool_result("diagnose_connection", obs)
        self._update_state_from_observation("diagnose_connection", obs)
        return True

    def ensure_action_done(self) -> bool:
        """Run the current strategy's ACTION step deterministically (engine-driven,
        not model-invoked), the same way ensure_diagnosed runs the first diagnose.

        Model-invoked update_mac caused two bugs: a single-tool loop (the bind step
        exposes only update_mac, so the model re-called it to the limit) and a
        contradictory narration (the model ignored the verified result and re-told
        the problem — "nepririštas, dabar pririšiu" — right after binding). Binding
        is a pure engine action: the engine runs it + reset_port + re-diagnose (via
        _augment_tool_result, which also sets case_closed on success or advances to
        escalate on failure), so by the time the LLM narrates it only PHRASES the
        verified outcome. Returns True if it ran an action this call."""
        s = self.state
        if not s.customer_id or s.case_closed:
            return False
        r = s.resolution
        if not r:
            return False
        from .resolution import StepKind, get_strategy

        strat = get_strategy(r.get("verdict"))
        step = strat.step(r.get("step", "")) if strat else None
        if step is None:
            return False
        # Auto-register ESCALATE (consent=False, e.g. dr_register_router after a working
        # bridge): the registration is a NECESSITY, not an offer — the engine registers
        # ON ARRIVAL and closes; the narrator only ANNOUNCES it ("užregistravau...,
        # kolegos susisieks ir detaliau paaiškins"). Asking permission here misread a
        # non-consent reply as a decline and the caller left WITHOUT the ticket they
        # were promised (observed live).
        # ESCALATE arrival (consented or not) begins the ticket dialogue THE SAME
        # TURN — deterministically. Leaving the arrival to the LLM narrator had it
        # claim "užregistravau…" before anything was registered and before the
        # contact questions (observed live 2026-08-04). The dialogue's intro
        # announces the registration; an explicit refusal during it still declines.
        if step.kind is StepKind.ESCALATE:
            self._begin_ticket_dialogue(step)  # contacts first, then register+close
            return True
        if step.kind != StepKind.ACTION:
            return False
        if r.get("action_done"):
            return False  # already ran this action; the walker advances it next turn
        ran = False
        for action in step.tool_actions:
            try:
                obs = execute_tool(action, {"customer_id": s.customer_id})
            except Exception:  # pragma: no cover - best-effort
                continue
            self.tracer.emit("tool_call", name=action, args={"customer_id": s.customer_id})
            obs = self._augment_tool_result(action, obs)  # chains reset_port + re-diagnose
            self._trace_tool_result(action, obs)
            ran = True
        if ran:
            r["action_done"] = True  # the announce is narrated this turn; advance next
        return ran

    def _advance_resolution(self, user_input: str | None) -> None:
        """Walk the strategy from the caller's reply, then trace WHY it moved (or did
        not) — the decision record is what makes a failed call debuggable."""
        # Ledger: a fresh evidence conflict holds the walker THIS turn — the
        # contradicting utterance must not double as a step answer; the scripted
        # clarification goes out instead and the settling answer resumes.
        if self._evidence_conflict:
            self.tracer.emit(
                "decision",
                intent="evidence_conflict",
                action="hold",
                key=self._evidence_conflict[0],
            )
            return
        r = self.state.resolution
        before = r.get("step") if r else None
        self._walk_resolution(user_input)
        self._emit_decision(before)

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
        """Compact situation snapshot the solver reasons over: the live hypothesis, the
        raw telemetry facts (line-side truth), the caller's latest turn, and where the
        walker currently is."""
        s = self.state
        h = s.hypothesis or {}
        net = s.diagnosis.get("network") or {}
        sig = net.get("signals") or {}
        r = s.resolution or {}
        lines: list[str] = []
        # Recent dialogue so the solver knows WHERE in the procedure it is (which steps
        # already happened) instead of re-reasoning from scratch each turn.
        recent = [
            m
            for m in s.messages
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
        ][-8:]
        if recent:
            convo = "\n".join(
                f"{'Klientas' if m['role'] == 'user' else 'Agentas'}: {m['content']}"
                for m in recent
            )
            lines.append(f"POKALBIS IKI ŠIOL:\n{convo}\n")
        lines.append(
            f'KLIENTAS KĄ TIK PASAKĖ: "{user_input or ""}" (intent={s.last_intent or "?"})'
        )
        if h:
            because = "; ".join(h.get("because", []) or [])
            lines.append(f"HIPOTEZĖ: {h.get('cause')} (status={h.get('status')}); nes: {because}")
        # The ANALYSIS (Step 2): the caller's half of the picture — the thinker reasons
        # from BOTH sides, not telemetry alone.
        if s.anamnesis_raw:
            bits = [f'žodžiais: "{s.anamnesis_raw}"']
            if s.anamnesis_when:
                bits.append(f"dingo {s.anamnesis_when}")
            if s.anamnesis_trigger:
                bits.append(f"po: {s.anamnesis_trigger}")
            lines.append("ANAMNEZĖ (klientas): " + "; ".join(bits))
        if s.symptoms:
            lines.append("SIMPTOMAI: " + ", ".join(f"{k}={v}" for k, v in s.symptoms.items()))
        if s.caller_name:
            lines.append(f"SKAMBINA: {s.caller_name} (ryšys su sutartimi: {s.caller_relation})")
        if net.get("reason"):
            lines.append(f"TELEMETRIJOS KANDIDATAS (verdict tree): {net.get('reason')}")
        if sig:
            keys = (
                "port_link",
                "switch_status",
                "observed_mac",
                "registered_mac",
                "crc_error_rate",
                "dhcp_status",
                "incident",
                "billing_suspended",
            )
            facts = ", ".join(f"{k}={sig.get(k)}" for k in keys if sig.get(k) is not None)
            if facts:
                lines.append(f"TELEMETRIJA (signalai): {facts}")
        # Evidence ledger (Ledger v1): what is already ESTABLISHED — the thinker
        # asks only for what is missing and never re-asks a settled fact.
        if s.evidence:
            from .evidence import summary_lt

            lines.append(f"ĮRODYMŲ ŽURNALAS (nustatyta — NEBEKLAUSK): {summary_lt(s.evidence)}")
        lines.append(
            f"WALKER dabar: verdict={r.get('verdict')} step={r.get('step')} awaiting={s.awaiting}"
        )
        # The full procedure for this fault (the solver reasons over the WHOLE playbook to
        # pick the next action — unlike the narrator, which sees one isolated step).
        if r.get("verdict"):
            from .playbook import full_doc
            from .resolution import get_strategy

            strat = get_strategy(r.get("verdict"))
            doc = full_doc(strat.rag_doc) if strat and strat.rag_doc else None
            if doc:
                lines.append(f"\nPROCEDŪRA (playbook — sek ja, kad vestum srautą):\n{doc}")
        return "\n".join(lines)

    def _shadow_solve(self, user_input: str | None) -> None:
        """SHADOW: compute the solver's decision and log it next to the walker's move.
        Never drives the reply. No-op unless SOLVER_SHADOW=on and a strategy is active."""
        if os.getenv("SOLVER_SHADOW", "off").lower() != "on":
            return
        if not self.state.resolution or self.state.case_closed:
            return
        try:
            from .gate import DEFAULT_POLICY, INTERNAL_ACTIONS, gate
            from .resolution import STRATEGIES
            from .solver import solve

            decision = solve(self._build_solver_context(user_input), model=self.config.model)
            r = self.state.resolution or {}
            step = r.get("step")

            # Counters the gate reasons over (owned here so the gate stays pure). Track
            # them even in shadow so the bailout/loop safeguards are exercised for real.
            self._solver_cycles = self._solver_cycles + 1 if step == self._solver_prev_step else 0
            self._solver_prev_step = step
            conf = decision.confidence if decision else 0.0
            self._solver_low_conf = (
                self._solver_low_conf + 1 if conf < DEFAULT_POLICY["confidence_floor"] else 0
            )
            if decision and decision.next_action in INTERNAL_ACTIONS:
                self._solver_internal_hops += 1
            else:
                self._solver_internal_hops = 0

            result = gate(
                decision,
                known_hypotheses=set(STRATEGIES),
                low_conf_streak=self._solver_low_conf,
                cycles_in_step=self._solver_cycles,
                internal_hops=self._solver_internal_hops,
            )
            self.tracer.emit(
                "shadow_decision",
                walker_verdict=r.get("verdict"),
                walker_step=step,
                solver=(decision.model_dump() if decision else None),
                gate={
                    "action": result.action,
                    "accepted": result.accepted,
                    "bailout": result.bailout,
                    "reason": result.reason,
                },
            )
        except Exception as e:  # shadow must never affect the live turn
            logger.warning(f"shadow solver failed: {e}")
            self._trace_note("solver_shadow", str(e))

    # --- Solver DRIVES (Phase 3.8 step 5a) -----------------------------------
    # Behind SOLVER_DRIVE (default off), for the piloted directions only, the solver runs
    # the turn: it reads the RAG playbook + dialogue + telemetry, decides the next action,
    # the gate validates + the engine executes safety actions by code, and the reply is the
    # solver's spoken text. The walker stays the default and handles every other direction.
    _SOLVER_DRIVE_VERDICTS = frozenset({"no_mac_observed"})  # pilot: dead-router / bridge
    _DRIVE_MAX_TURNS = 14  # hard bailout — never grind the caller forever

    def _ingest_client_evidence(self, user_input: str | None) -> None:
        """Ledger v1: read the caller's utterance into the evidence ledger (called
        from the diagnosis node, so BOTH the driven and the walker path see it).
        A contradicting canonical value flags a conflict -> ONE scripted
        clarification; the next answer for that key settles it (extraction, or a
        bare yes/no polarity read; nothing readable -> the pending value wins so
        the call never loops on the clarify)."""
        s = self.state
        if not user_input or not s.customer_id or s.case_closed or self._ticket_stage:
            return
        from .evidence import CLIENT, extract_client_facts, polarity, set_fact

        facts = extract_client_facts(user_input)
        turn = s.turn_count
        # A clarify is out — settle that key first.
        pending_key = self._evidence_conflict_asked
        if pending_key:
            value = facts.get(pending_key)
            if value is None and pending_key == "has_computer":
                value = polarity(user_input)
            entry = s.evidence.get(pending_key)
            if value is not None:
                set_fact(s.evidence, pending_key, value, CLIENT, turn)
            elif entry is not None and entry.get("conflict"):
                # Unreadable answer — keep the LATEST stated value, stop asking.
                set_fact(s.evidence, pending_key, entry.get("pending"), CLIENT, turn)
            self._evidence_conflict_asked = None
            self.tracer.emit(
                "evidence",
                action="conflict_resolved",
                key=pending_key,
                value=(s.evidence.get(pending_key) or {}).get("value"),
            )
            facts.pop(pending_key, None)
        for key, value in facts.items():
            entry = set_fact(s.evidence, key, value, CLIENT, turn)
            if entry.get("conflict") and self._evidence_conflict is None:
                self._evidence_conflict = (key, entry["value"], entry["pending"])
                self.tracer.emit(
                    "evidence",
                    action="conflict",
                    key=key,
                    old=entry["value"],
                    new=entry["pending"],
                )
            else:
                self.tracer.emit("evidence", action="fact", key=key, value=value)

    def solver_drive_turn(self, user_input: str | None) -> str | None:
        """Solver-driven turn — the MĄSTYTOJAS drives the piloted directions (Step 3,
        default ON since 2026-08-03; SOLVER_DRIVE=off reverts to the walker). Returns
        the reply text, or None to fall back to the walker (no strategy, not a piloted
        direction, a solver failure — or DETERMINISTIC MECHANICS in progress: the
        identification ladder, the clarify contract and the wrap-up stay engine-owned,
        the thinker never overrides them)."""
        if os.getenv("SOLVER_DRIVE", "on").lower() != "on":
            return None
        r = self.state.resolution
        if not r or self.state.case_closed:
            return None
        if r.get("verdict") not in self._SOLVER_DRIVE_VERDICTS:
            return None
        # Engine mechanics first: while the ladder / clarify flow owns the turn, the
        # thinker waits (scripted replies and guards are deterministic territory).
        if self._result_pending or self._end_confirm_pending or self._resume_hold:
            return None
        if self._ticket_stage:
            return None  # the ticket dialogue owns the turn
        if self._evidence_conflict:
            return None  # the scripted conflict clarification owns the turn
        from .identification import ask_caller

        if ask_caller() and not self.state.caller_name:
            return None  # identification ladder not finished yet
        # Discipline rule (2026-08-05): "no device" after the bridge OFFER is
        # ENGINE territory — with nothing to bridge through, the only solutions
        # are ticket-shaped, so escalate NOW. Left to the solver, this answer
        # spawned a disambiguate streak ("patikrinkime dar kartą…" x6) and,
        # after the bailout, a full walker rewind to dr_intro (observed live).
        from .resolution import detect_no_device

        last_q = (self._last_agent_question() or "").lower()
        if "kompiuter" in last_q and detect_no_device(user_input):
            self.tracer.emit(
                "drive_decision",
                action="escalate",
                accepted=True,
                reason="no device after bridge offer — deterministic",
            )
            reply = self._drive_escalate(None)
            if user_input:
                self.state.last_heard = user_input.strip()
                self.tracer.emit("user_turn", text=user_input)
                self.state.messages.append({"role": "user", "content": user_input})
            self.state.messages.append({"role": "assistant", "content": reply})
            self._finalize_reply(reply)
            return reply
        # Distrust-loop bailout (deterministic): the solver repeated itself or kept
        # re-confirming ("disambiguate") turn after turn despite clear answers — the
        # prompt rule did not hold it (observed live: 6x "patikrinkime dar kartą…";
        # in eval: 6/8 turns of variously-worded disambiguate). The promised backstop
        # takes over: the DETERMINISTIC WALKER resumes this direction for the rest of
        # the call; its own guards (stuck counter, escalate) handle the endgame.
        if getattr(self, "_drive_disabled", False):
            return None
        if getattr(self, "_drive_repeats", 0) >= 2:
            self._drive_disabled = True
            self._drive_repeats = 0
            self._drive_last_reply = None
            self.tracer.emit(
                "drive_decision",
                action="bailout_to_walker",
                accepted=False,
                reason="distrust loop (repeat/disambiguate streak)",
            )
            self._trace_note("solver_drive", "distrust loop — walker resumes", level="warn")
            return None  # the walker takes this and every following turn
        try:
            reply = self._drive(user_input)
        except Exception as e:  # a solver failure falls back to the walker (no bookkeeping yet)
            logger.error(f"solver drive failed: {e}")
            self._trace_note("solver_drive", str(e), level="error")
            return None
        # Committed to driving this turn — do the same end-of-turn bookkeeping the walker
        # path gets from run_turn_scoped: user_turn trace, dialogue history (the solver reads
        # it next turn), and the shared reply finalisation (case snapshot + agent_reply).
        if user_input:
            self.state.last_heard = user_input.strip()
            self.tracer.emit("user_turn", text=user_input)
            self.state.messages.append({"role": "user", "content": user_input})
        self.state.messages.append({"role": "assistant", "content": reply})
        self._finalize_reply(reply)
        return reply

    def _drive(self, user_input: str | None) -> str:
        from .gate import DEFAULT_POLICY, gate
        from .resolution import STRATEGIES, detect_turn_intent
        from .solver import solve

        self.state.last_intent = detect_turn_intent(user_input)
        self._drive_turns = getattr(self, "_drive_turns", 0) + 1

        context = self._build_solver_context(user_input)
        # Anti-repeat nudge: last reply repeated an earlier one — tell the solver the
        # answer is already GIVEN and it must take a DIFFERENT next step.
        if getattr(self, "_drive_repeats", 0) >= 1:
            context += (
                "\nSVARBU: tavo praėjęs klausimas KARTOJOSI, o klientas jau atsakė ir "
                "patvirtino. PRIIMK tą atsakymą kaip faktą ir ženk KITĄ žingsnį (kita "
                "hipotezė, pasiūlymas ar registracija) — to paties NEBEKLAUSK."
            )
        # A few internal (silent) hops are allowed — reread/pivot re-read the line — before
        # a client-facing action is forced. Hard turn cap escalates rather than looping.
        for _ in range(DEFAULT_POLICY["internal_hops_max"] + 1):
            decision = solve(context, model=self.config.model)
            # Normalize the free-form hypothesis to the ACTIVE direction before the
            # gate: the solver words the same belief freely ("routeris sugedęs,
            # nes…"), and the gate then blocked the direction's OWN fix as a
            # "mutation on unmapped hypothesis" — the announced bind never ran
            # (observed: "pririšiu" spoken, update_mac not called). Working the SAME
            # fault in other words is not a new hypothesis; a real pivot names a
            # DIFFERENT known cause, which stays gated.
            if decision is not None and decision.current_hypothesis not in STRATEGIES:
                decision = decision.model_copy(
                    update={
                        "current_hypothesis": (self.state.resolution or {}).get("verdict") or ""
                    }
                )
            conf = decision.confidence if decision else 0.0
            self._solver_low_conf = (
                self._solver_low_conf + 1 if conf < DEFAULT_POLICY["confidence_floor"] else 0
            )
            forced = self._drive_turns > self._DRIVE_MAX_TURNS
            result = gate(
                decision,
                known_hypotheses=set(STRATEGIES),
                low_conf_streak=self._solver_low_conf,
                # The REAL per-question cycle count (the same-reply streak) — with a
                # flat 0 here the gate's stuck detector was blind and the solver
                # looped one question 6x (observed live).
                cycles_in_step=(
                    self._DRIVE_MAX_TURNS + 1 if forced else getattr(self, "_drive_repeats", 0)
                ),
                internal_hops=self._solver_internal_hops,
            )
            action = result.action
            self.tracer.emit(
                "drive_decision",
                action=action,
                accepted=result.accepted,
                bailout=result.bailout,
                reason=result.reason,
                hypothesis=(decision.current_hypothesis if decision else None),
                confidence=conf,
            )
            say = (decision.narrator_instruction if decision else "").strip()
            # Never SPEAK an instruction whose action the gate overrode — the words
            # would promise what will not run ("pririšiu" with the bind blocked).
            if decision is not None and not result.accepted:
                say = ""

            if action in ("reread_telemetry", "pivot"):
                self._solver_internal_hops += 1
                self._refresh_diagnosis()  # re-read the line, then decide again
                continue
            self._solver_internal_hops = 0

            if action == "propose_fix":
                return self._drive_propose_fix(say, user_input)
            if action == "escalate":
                return self._drive_escalate(decision)
            if action == "close":
                self.state.case_closed = True
                self.state.closed_reason = "resolved"
                self._settle_hypothesis("confirmed", "sprendimas suveikė (solveris)")
                return say or "Puiku, džiaugiuosi, kad sutvarkėme!"
            # client-facing: ask / disambiguate / instruct / verify / wait — track the
            # DISTRUST streak so the next turn's nudge/gate/bailout see the loop:
            # a verbatim repeat OR consecutive disambiguates (any wording) count.
            defaults = {
                "verify": "Patikrinkite, prašau, ar internetas jau atsirado.",
                "wait": "Gerai, palauksiu — pasakykite, kai būsite pasiruošę.",
            }
            reply = say or defaults.get(action, "Atsiprašau, ar galėtumėte pakartoti?")
            norm = " ".join(reply.lower().split())
            repeated = norm == getattr(self, "_drive_last_reply", None)
            re_disambiguate = (
                action == "disambiguate"
                and getattr(self, "_drive_last_action", None) == "disambiguate"
            )
            if repeated or re_disambiguate:
                self._drive_repeats = getattr(self, "_drive_repeats", 0) + 1
            else:
                self._drive_repeats = 0
            self._drive_last_reply = norm
            self._drive_last_action = action
            return reply
        return "Sekundėlę — patikslinkim dar kartą."

    def _refresh_diagnosis(self) -> None:
        """Re-read the line so the solver reasons over CURRENT telemetry (fixes the stale-
        snapshot issue). Keeps the active strategy; only refreshes the signals."""
        self.state.diagnosis.pop("network", None)
        self.ensure_diagnosed()

    def _drive_propose_fix(self, say: str, user_input: str | None) -> str:
        """Execute the bind the solver proposed — under DISCIPLINE (Andrius,
        2026-08-04): a change runs ONLY when the client actually DID the work and
        thereby agreed to it. The solver anticipated the playbook's ending and had the
        engine bind FOUR turns early (before the caller even said they own a computer
        — observed live). Preconditions, in order:
          1. the caller's CURRENT turn reports a completed plug-in ("įkišau…"), OR the
             line already OBSERVES a device (production: it shows up on its own);
             otherwise -> no tools, keep instructing;
          2. never twice — a completed bind is recorded and not repeated;
          3. after the (demo) simulation, bind only if a device is actually observed —
             never bind blind."""
        from .resolution import detect_plugged

        cid = self.state.customer_id
        if getattr(self, "_bridge_bound", False):
            return say or "Įrenginys jau pririštas — patikrinkite, ar internetas atsirado."

        def _device_visible() -> bool:
            # The tool's verdict envelope carries no signals — device presence is read
            # from the REASON: "no_mac_observed" = the line still sees nothing; any
            # other verdict (foreign_mac after the plug-in) = a device is there.
            try:
                d = json.loads(execute_tool("diagnose_connection", {"customer_id": cid}))
                return ((d.get("verdict") or {}).get("reason")) != "no_mac_observed"
            except Exception:  # pragma: no cover - best-effort read
                return False

        if not detect_plugged(user_input) and not _device_visible():
            # The work is not done yet — the fix must WAIT for the client. And the
            # FIRST deferral must be the actual TRANSITION + OFFER: live 2026-08-05
            # the solver jumped straight to bind-speak ("pririšiu įrenginį") without
            # ever saying the router is dead or asking about a computer — the caller
            # answered "Apie kokį kompiuterį kalbat?".
            self.tracer.emit(
                "drive_decision", action="fix_deferred", accepted=False, reason="not plugged yet"
            )
            if not getattr(self, "_drive_bridge_offered", False):
                self._drive_bridge_offered = True
                return (
                    "Panašu, kad routeris sugedęs — telefonu jo neprikelsime. Galiu "
                    "laikinai paleisti internetą per kompiuterį, kol gausite naują "
                    "routerį. Ar turite kompiuterį?"
                )
            return "Kai prijungsite kabelį prie kompiuterio, pasakykite — tada pririšiu įrenginį."
        self._simulate_bridge_connection()
        # Bind only when the line ACTUALLY sees a device now (never blind).
        if not _device_visible():
            self.tracer.emit(
                "drive_decision", action="fix_deferred", accepted=False, reason="no device observed"
            )
            return (
                "Kol kas linijoje dar nematome jūsų kompiuterio — patikrinkite, ar "
                "kabelis įkištas iki galo, ir pasakykite."
            )
        try:
            obs = execute_tool("update_mac", {"customer_id": cid})
            self.tracer.emit("tool_call", name="update_mac", args={"customer_id": cid})
            self._augment_tool_result("update_mac", obs)  # chains reset_port + re-diagnose
            self._bridge_bound = True
        except Exception as e:
            self._trace_note("drive_propose_fix", str(e), level="error")
        return (
            say
            or "Matau jūsų kompiuterį linijoje — pririšau. Patikrinkite, ar internetas atsirado."
        )

    def _drive_escalate(self, decision) -> str:
        """Register the fault and close — through the SAME state-built ticket machinery
        as everywhere else (its ad-hoc create_ticket used to write a raw verdict key as
        the details, lose ticket_id from the record, and then ASK permission for a
        ticket it had already created — observed live). The announce is deterministic:
        the ticket exists, so the words state a fact, never ask."""
        from .resolution import get_strategy

        s = self.state
        r = s.resolution or {}
        strat = get_strategy(r.get("verdict"))
        # The bridge already restored internet on the PC -> this is the
        # register-router shape (temporary bridge note rides on the ticket).
        bridged = bool(r.get("telemetry_fixed")) or getattr(self, "_bridge_bound", False)
        step = None
        if strat is not None:
            step = strat.step("dr_register_router") if bridged else strat.step("escalate")
            if step is None:
                step = strat.step("escalate")
        if not r.get("escalate_reason"):
            r["escalate_reason"] = "Sprendimas telefonu nepavyko."
        # Contacts first (2026-08-04): the dialogue collects the number + hours, then
        # _finish_ticket_dialogue registers and closes. The bridged note rides on the
        # final announce via the ctx.
        self._begin_ticket_dialogue(step)
        if self._ticket_ctx is not None and bridged:
            self._ticket_ctx["note"] = (
                " Internetas kol kas veiks per kompiuterį; kai turėsite naują routerį, "
                "paskambinkite — pririšime, ir veiks visi namai."
            )
        return self._ticket_stage_reply()

    def _walk_resolution(self, user_input: str | None) -> None:
        """Generic step-by-step walker over the active strategy, from the caller's
        reply. Uniform for all fault types:

        - INSTRUCT / ACTION: a guided step. Once its instruction (or the bind
          announce) has been presented, ANY caller reply — they did it / answered —
          advances to the next step. One instruction per turn, listen, move on.
        - CONFIRM: branches on yes/no (and a strong device-change pre-answer).
        - confirm_restored: a VERIFY that blends the caller's word with a fresh
          telemetry read — routed separately (_advance_restored).

        This is what leads the caller one step at a time instead of dumping the
        whole playbook, and stops the model binding a device they never confirmed."""
        from .resolution import (
            StepKind,
            confirms_device_change,
            get_strategy,
            next_step_id,
        )

        r = self.state.resolution
        if not r or self.state.case_closed:
            return
        # One-turn hold after the caller declined to end the call — their "ne,
        # tęskime" answers the confirm-end question, not the current step.
        if self._resume_hold:
            self._resume_hold = False
            return
        # Derive the intent from THIS call's input rather than trusting it was set
        # earlier — the walker must not depend on the caller's ordering.
        from .resolution import detect_turn_intent

        self.state.last_intent = detect_turn_intent(user_input)
        strat = get_strategy(r.get("verdict"))
        step = strat.step(r.get("step", "")) if strat else None
        if step is None:
            return
        # A strong device-change signal advances confirm_change before it is even asked
        # (the caller pre-answered, e.g. "neveikia, keičiau routerį"). ONLY for that step —
        # elsewhere "kompiuteris" is a scope answer, not a device change. Runs before the
        # intent gate: a clear pre-answer should move regardless of turn phrasing.
        if step.id == "confirm_change" and confirms_device_change(user_input):
            self._route_to(r, next_step_id(strat, step.id, "yes"))
            return
        # Backchannel guard: a bare "Mhm." / one-letter STT crumb is an acknowledgement,
        # not an answer — HOLD asking steps instead of routing garbage (observed: "T."
        # entered the bridge path as "yes, I have a computer"; "Mhm." climbed two
        # INSTRUCT steps). ACTION steps still advance — their announce needs no answer.
        if step.kind in (StepKind.CONFIRM, StepKind.INSTRUCT):
            from .resolution import is_backchannel

            if is_backchannel(user_input):
                self.tracer.emit(
                    "decision", intent="backchannel", action="hold", from_step=step.id, to=step.id
                )
                return
        # A clear "atsirado / veikia" pre-answers a restored CONFIRM before it was even
        # asked — often fused with the goodbye ("yra internetas, ačiū, viso gero"). Route
        # the YES so the resolve is RECORDED instead of the call dying unclosed on the
        # hangup (observed live: resolved Wi-Fi call left outcome=None). Only the clear
        # affirmative pre-answers; a "no" still waits for the step's own question.
        if step.detector == "restored" and not r.get("asked"):
            from .resolution import Outcome, detect_restored

            if detect_restored(user_input) is Outcome.YES:
                self._route_to(r, next_step_id(strat, step.id, "yes"))
                return
        # Refusal / explicit ticket demand ends troubleshooting in a REGISTRATION
        # (policy 2026-07-30). A clear DEMAND ("įregistruokit gedimą") IS the consent —
        # register now and close, with the reason on the ticket. A softer refusal
        # ("nedarysiu", "nesu namuose") routes to the escalate step, whose consent
        # question doubles as the polite clarification ("užregistruosiu — ar tinka?").
        # Observed live: the caller demanded a ticket 3×, the narrator promised it 5×,
        # and the walker held cable_check forever — no route existed.
        if step.kind is not StepKind.ESCALATE:
            from .resolution import detect_refuse_or_ticket

            rt = detect_refuse_or_ticket(user_input)
            if rt is not None and strat.step("escalate") is not None:
                r["escalate_reason"] = (
                    "Klientas paprašė registracijos."
                    if rt == "demand"
                    else "Neišspręsta — klientas atsisakė tęsti tikrinimą."
                )
                self._goto_step(r, "escalate")
                self.tracer.emit(
                    "decision",
                    intent="refuse_or_ticket",
                    action=rt,
                    from_step=step.id,
                    to="escalate",
                )
                if rt == "demand":
                    self._begin_ticket_dialogue(strat.step("escalate"))
                return
        # ASKED generic CONFIRM (yes/no, lights, scope, restored, …): the LLM classifier
        # reads the answer AND whether it IS an answer in one call — so a confident answer
        # advances even when the brittle keyword turn-intent would veto it (observed:
        # "gerai, bandau… nė viena lemputė neužsidegė" was read as in_progress and froze
        # dr_power). The keyword detector + intent gate below stay as the fallback.
        if (
            step.kind is StepKind.CONFIRM
            and r.get("asked")
            and step.on
            and step.id != "confirm_restored"
            and os.getenv("CLASSIFIER", "on").lower() != "off"
        ):
            if self._classify_confirm_and_route(step, strat, user_input):
                return
        # ASKED INSTRUCT: the LLM classifier decides done-vs-still-doing, so a clear "I did
        # it" phrased messily ("Gerai, jau įkišau") advances even when the keyword
        # turn-intent reads it as in_progress and freezes the step (observed: dr_plug_pc
        # froze, the bridge never bound). Keyword intent gate below stays the fallback.
        if (
            step.kind is StepKind.INSTRUCT
            and r.get("asked")
            and os.getenv("CLASSIFIER", "on").lower() != "off"
        ):
            if self._classify_instruct_and_advance(step, strat, user_input):
                return
        # ESCALATE = deterministic OUTCOME (Phase 3.11 B). The step is a call-ending
        # consent question ("užregistruosiu gedimą — ar tinka?"): the ENGINE registers
        # the ticket from STATE on consent and closes; a decline closes without a
        # ticket. create_ticket is no longer an LLM-callable tool mid-strategy, so the
        # model can neither freelance a ticket nor loop the consent question (observed
        # live: 4× "ar tinka?" — the ticket only landed via the gate bailout).
        if step.kind is StepKind.ESCALATE:
            self._advance_escalate(r, step, user_input)
            return
        # What KIND of turn was this? Only a real answer or a completed action may move
        # the conversation. "Einu prie routerio", a question, confusion or silence all
        # HOLD the step — the agent responds to them instead of running ahead.
        if not self._turn_may_advance(step):
            return
        # confirm_restored blends the caller's word with a fresh telemetry read.
        if step.id == "confirm_restored":
            self._advance_restored(r, user_input)
            return
        # Bridge: did the device they just plugged in actually appear on the line?
        if step.id == "dr_see_device":
            self._advance_see_device(r)
            return
        # A guided instruction / the bind announce: advance on ANY reply, once it was
        # presented last turn — to an explicit goto if set, else the next step in order.
        if step.kind in (StepKind.INSTRUCT, StepKind.ACTION):
            if r.get("asked"):
                self._advance_instruct(r, step, strat, user_input)
            return
        if step.kind != StepKind.CONFIRM:
            return
        # Otherwise route only once the question was asked — a bare "taip" on the
        # diagnose turn is the address confirmation, not an answer to this step.
        if not r.get("asked"):
            return
        # Keyword fallback (classifier off / unsure): read the reply into a routing key.
        key = self._detect_confirm(step, user_input)
        if key is None:
            return
        self._route_to(r, next_step_id(strat, step.id, key))

    def _emit_rag_injection(self, doc: str | None, section: int, step_id: str, text: str) -> None:
        """Emit a `rag` trace event when a playbook section is injected for a step —
        deduped on (doc, section, step) so the multi-call turn (LLM + tool follow-up)
        logs it once, and a step change logs the new section."""
        key = (doc, section, step_id)
        if getattr(self, "_last_rag_key", None) == key:
            return
        self._last_rag_key = key
        preview = " ".join((text or "").split())[:90]
        self.tracer.emit("rag", doc=doc, section=section, step=step_id, preview=preview)

    def _pre_turn_guards(self, user_input: str) -> None:
        """Deterministic per-turn guards, run BEFORE the LLM sees the turn.

        (1) Address-offer reply guard: a reply to "Ar skambinate dėl X?" commits the
            account ONLY on a CLEAN yes — a garbled/mixed reply ("Taip, nebija" = STT
            mangle of a denial) vetoes the commit and the agent re-asks (observed live:
            wrong apartment's debt read to the caller).
        (2) Reopen identification: an already-identified caller says they are calling
            about a DIFFERENT address -> drop the identity and ask for the address
            again instead of carrying on about the wrong account."""
        s = self.state
        self._addr_confirm_note = None
        self._reopen_note = False
        if not user_input:
            return
        # (-2) Ticket-dialogue capture: the previous scripted reply asked for the
        # contact number / hours — read the answer. A question falls through to the
        # LLM (the stage stays and re-asks); a farewell fast-forwards with defaults
        # (the caller is done talking — register with what we have).
        if self._ticket_stage in ("phone", "hours"):
            from .resolution import detect_farewell, detect_ticket_consent

            self._ticket_offscript = False
            low_q = (user_input or "").lower()
            # A QUESTION diverts to the ticket node's LLM (it answers + re-asks the
            # stage question) — "Bet kada galima skambinti?" was swallowed as the
            # HOURS answer live and landed verbatim on the ticket. Bare "kada" stays
            # an answer word ("bet kada"), so it is deliberately not in this list.
            if any(
                m in low_q
                for m in (
                    "kodėl",
                    "kodel",
                    "kiek",
                    "kam ",
                    "kas čia",
                    "kas cia",
                    "kokiu",
                    "koks ",
                    "kokia ",
                    "galima",
                    "ar ",
                )
            ):
                self._ticket_offscript = True
                self.tracer.emit("decision", intent="ticket_dialogue", action="question")
                return
            # Explicit "do not register" cancels the dialogue (their call, their
            # choice) — the scripted reply closes with a goodbye.
            if any(
                m in low_q
                for m in ("neregistruok", "nereikia regi", "nereikia tiket", "atšauk", "atsauk")
            ):
                self._ticket_stage = "cancelled"
                self.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                return
            if detect_farewell(user_input):
                self._ticket_stage = "done"
                return
            ctx = self._ticket_ctx if self._ticket_ctx is not None else {}
            # An answer counts ONLY after its question was actually ASKED. The
            # dialogue can begin mid-turn (escalate fires while processing the
            # caller's utterance) — live 2026-08-05 the TRIGGER phrase "Neturi
            # kompiutera" was swallowed as the phone number.
            if not ctx.get(f"{self._ticket_stage}_asked"):
                return
            clean = user_input.strip().strip(" .?!,")
            if self._ticket_stage == "phone":
                from .resolution import is_backchannel

                digits = re.sub(r"[^\d+]", "", user_input)
                if len(re.sub(r"\D", "", digits)) >= 6:
                    s.contact_phone = digits[:20]
                elif detect_ticket_consent(user_input) == "yes" or is_backchannel(user_input):
                    # "tiks šis" / a garbled yes ("T." — STT of "Taip", observed
                    # live as tel. on the ticket) — the number they call from.
                    s.contact_phone = s.caller_phone
                elif ctx.get("phone_retry"):
                    # Second unclear answer — default to the caller-ID and move on.
                    s.contact_phone = s.caller_phone
                else:
                    # Not a number, not a yes — the agent SAYS what it needs and
                    # re-asks ONCE ("understand the answer, re-ask when it is not
                    # one" — 2026-08-05); garbage never lands on the ticket.
                    ctx["phone_retry"] = True
                    ctx["ask_retry"] = "phone"
                    self.tracer.emit("decision", intent="ticket_dialogue", action="phone_retry")
                    return
                self.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
                self._ticket_stage = "hours"
            else:
                low_h = clean.lower()
                plausible = bool(re.search(r"\d", low_h)) or any(
                    m in low_h
                    for m in (
                        "bet kada",
                        "bet kad",
                        "kada nor",
                        "visada",
                        "ryt",
                        "vakar",
                        "val",
                        "darbo",
                        "diena",
                        "dien",
                        "po ",
                        "iki ",
                        "nuo ",
                        "savait",
                        "pirmad",
                        "antrad",
                        "trečiad",
                        "treciad",
                        "ketvirtad",
                        "penktad",
                        "šeštad",
                        "sestad",
                        "sekmad",
                        "dabar",
                        "šiandien",
                        "siandien",
                    )
                )
                if not plausible and not ctx.get("hours_retry"):
                    ctx["hours_retry"] = True
                    ctx["ask_retry"] = "hours"
                    self.tracer.emit("decision", intent="ticket_dialogue", action="hours_retry")
                    return
                # Strip trailing STT punctuation — "Bet kada?" landed on the ticket
                # (and in the announce) with the question mark. Second unclear
                # answer defaults to "bet kada" (spoken back in the announce).
                s.contact_hours = clean[:80] if plausible else "bet kada"
                self.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
                self._ticket_stage = "done"
            return
        # (-1) Farewell mid-process is a signal to CLARIFY, never to close (policy
        # 2026-08-03): "viso gero" heard during identification / troubleshooting /
        # before the news gets ONE confirm question; only the confirmation ends the
        # call — through the outcome (registration when a strategy is active).
        from .resolution import detect_farewell, detect_ticket_consent

        if self._end_confirm_pending and not s.case_closed:
            self._end_confirm_pending = False
            if detect_farewell(user_input) or detect_ticket_consent(user_input) == "yes":
                if s.resolution is not None:
                    from .resolution import get_strategy

                    strat = get_strategy(s.resolution.get("verdict"))
                    esc = strat.step("escalate") if strat else None
                    s.resolution["escalate_reason"] = "Klientas nutraukė pokalbį."
                    if esc is not None:
                        self._begin_ticket_dialogue(esc)  # contacts, then register+close
                    else:
                        s.case_closed = True
                        s.closed_reason = "declined"
                else:
                    s.case_closed = True
                    s.closed_reason = "declined"
                self.tracer.emit("decision", intent="end_confirmed", action="close")
            else:
                # Changed their mind — hold the walker THIS turn so a "ne, tęskime"
                # is not misrouted as a step answer; resume next turn.
                self._resume_hold = True
                self.tracer.emit("decision", intent="end_declined", action="resume")
            return
        mid_process = not s.case_closed and (
            not s.customer_id
            or s.resolution is not None
            or self._result_pending
            or (bool(s.diagnosis) and not (self._news_told or s.outage_reported))
        )
        if mid_process and detect_farewell(user_input):
            self._end_confirm_pending = True
            self.tracer.emit("decision", intent="farewell_mid_process", action="confirm_end")
            return
        # (0) Caller-intro capture: the previous reply asked WHO is calling (the
        # identification ladder's last rung) — record the answer verbatim (for the
        # RECORD, 5d rule) + a keyword relation read. The deferred check result goes
        # out in THIS turn's reply (see the RESULT facts directive).
        if s.customer_id and self._result_pending and not s.caller_name:
            from .identification import detect_caller_relation
            from .resolution import detect_farewell, is_real_question

            # Question by WORDS only — STT sticks "?" onto rising intonation
            # ("Tomas? Ne, mano vardas Tomas…" is the ANSWER, not a question).
            if is_real_question(user_input):
                return  # off-script — the LLM answers; the ladder re-asks next turn
            if not detect_farewell(user_input):
                # Wait/consent-only replies are NOT a name ("Taip.", "Laukiu, laukiu"
                # were captured as names live) — record "nenurodyta" and move on.
                tokens = [t.strip(".,!?") for t in user_input.lower().split()]
                _NOT_A_NAME = {
                    "taip",
                    "ne",
                    "gerai",
                    "laukiu",
                    "aha",
                    "mhm",
                    "jo",
                    "ačiū",
                    "aciu",
                    "ok",
                    "okey",
                    "nesu",
                    "na",
                    "nu",
                    "tai",
                }
                if tokens and all(t in _NOT_A_NAME for t in tokens if t):
                    s.caller_name = "nenurodyta"
                    s.caller_relation = "unknown"
                else:
                    # The bare NAME, not the sentence — "Taip. Mano vardas Andrius.
                    # Taip, aš sutartį sudaręs asmuo." went on the ticket verbatim.
                    from .identification import extract_caller_name

                    s.caller_name = extract_caller_name(user_input) or user_input.strip()[:120]
                    s.caller_relation = detect_caller_relation(user_input)
                self.tracer.emit("caller_intro", name=s.caller_name, relation=s.caller_relation)
            return
        if not s.customer_id:
            q = (self._last_agent_question() or "").lower()
            if "skambinate dėl" in q or "dėl šio adreso" in q or "adreso skambinate" in q:
                from .resolution import detect_address_confirm

                verdict = detect_address_confirm(user_input)
                if verdict == "yes" and s.phone_candidate and s.phone_candidate.get("street"):
                    # Clean YES to the phone-address OFFER: the ENGINE commits the
                    # identity from the candidate parts right now (the model's own
                    # resolve-then-narrate path kept relapsing into confirm rounds
                    # and skipping the caller question — observed live). The scripted
                    # ladder reply asks WHO is calling next.
                    c = s.phone_candidate
                    p = s.profile
                    from .slots import SlotStatus

                    p.street.propose(c["street"], 1.0, SlotStatus.HEARD)
                    p.house.propose(str(c.get("house") or ""), 1.0, SlotStatus.HEARD)
                    if c.get("apartment"):
                        p.apartment.propose(str(c["apartment"]), 1.0, SlotStatus.HEARD)
                    if c.get("city"):
                        p.city.propose(str(c["city"]), 1.0, SlotStatus.HEARD)
                    if self._engine_resolve_from_slots():
                        self._trace_note("address_confirm", "offer confirmed; engine resolve")
                        self._just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.caller_name:
                            self._result_pending = True
                    return
                if verdict != "yes":
                    # Direct accept (arc v3.1): the caller DICTATED a full other address
                    # in this very turn (NLU heard street+house clearly) — the ENGINE
                    # resolves + diagnoses it RIGHT NOW (asking the model to call the
                    # tool proved unreliable: it narrated "patikrinsiu" without acting,
                    # then relapsed into a redundant confirm round). The reply then
                    # echoes the address and continues per the identification ladder.
                    p = self.state.profile
                    # Street/city inherit from the OFFERED address when the correction
                    # names only the house/flat ("Ne, dėl 60 buto 3" — same street;
                    # observed live: the engine path did not fire without this).
                    if not p.street.value and p.house.value and s.phone_candidate:
                        from .slots import SlotStatus

                        if s.phone_candidate.get("street"):
                            p.street.propose(s.phone_candidate["street"], 0.9, SlotStatus.HEARD)
                        if not p.city.value and s.phone_candidate.get("city"):
                            p.city.propose(str(s.phone_candidate["city"]), 0.9, SlotStatus.HEARD)
                    if p.street.value and p.house.value:
                        self._trace_note(
                            "address_confirm",
                            "offer corrected with a full dictated address; engine resolve",
                        )
                        if self._engine_resolve_from_slots():
                            self._just_identified = True
                            from .identification import ask_caller

                            if ask_caller() and not s.caller_name:
                                self._result_pending = True
                            self._addr_confirm_note = (
                                "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                                f"adresas {s.customer_address}. Atsakymo pradžioje "
                                "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                                "pagal žemiau esančią kryptį."
                            )
                        else:
                            self._addr_confirm_note = (
                                "- KLIENTAS PASAKĖ KITĄ ADRESĄ, bet jo patikrinti "
                                "nepavyko (žr. HEARD ADDRESS) — patikslink trūkstamą "
                                "dalį arba paprašyk pakartoti."
                            )
                    else:
                        self._addr_confirm_note = (
                            "- ADRESAS NEPATVIRTINTAS: kliento atsakymas AIŠKIAI "
                            "nepatvirtino pasiūlyto adreso (girdisi neigimas ar "
                            "neaiškumas). NEkviesk resolve_address su pasiūlytu adresu. "
                            "Jei klientas įvardijo KITĄ adresą (žr. HEARD ADDRESS) — "
                            "naudok TĄ. Kitu atveju mandagiai perklausk: „Atsiprašau, "
                            "nesupratau — dėl kokio adreso skambinate?“"
                        )
                        self._trace_note(
                            "address_confirm",
                            f"offer not confirmed (verdict={verdict}); veto commit",
                            level="warn",
                        )
        elif not s.case_closed:
            from .resolution import detect_address_correction

            if detect_address_correction(user_input):
                self._reopen_identification(user_input)

    def _engine_resolve_from_slots(self) -> bool:
        """Deterministic identification commit from clearly-heard slots: the ENGINE
        calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
        hesitancy, no confirm-round relapse. True when a customer committed."""
        p = self.state.profile
        args: dict[str, str] = {
            "street": str(p.street.value),
            "house_number": str(p.house.value),
        }
        if p.apartment.value:
            args["apartment_number"] = str(p.apartment.value)
        if p.city.value:
            args["city"] = str(p.city.value)
        try:
            obs = execute_tool("resolve_address", args)
        except Exception as e:  # pragma: no cover - best-effort
            self._trace_note("engine_resolve", str(e), level="error")
            return False
        self.tracer.emit("tool_call", name="resolve_address", args=args)
        self._trace_tool_result("resolve_address", obs)
        self._update_state_from_observation("resolve_address", obs)
        if not self.state.customer_id:
            return False
        self.ensure_diagnosed()
        return True

    def _reopen_identification(self, user_input: str) -> None:
        """The caller corrected the address AFTER identification — drop the identity and
        every per-account conclusion; keep only the conversation. The router sends the
        next turn back to address_validation (customer_id is None again)."""
        s = self.state
        self._trace_note(
            "reopen_identity",
            f"caller says a DIFFERENT address; dropping {s.customer_id}",
            level="warn",
        )
        s.customer_id = None
        s.customer_name = None
        s.customer_address = None
        s.address_confirmed = False
        s.resolution = None
        s.diagnosis.clear()
        s.hypothesis = None
        s.failed_hypotheses.clear()
        s.rejected_hypotheses.clear()
        s.pivoted_from = None
        s.outage_reported = False
        from .slots import ClientProfileState

        s.profile = ClientProfileState()
        self._db_address_note = None
        self._news_told = False  # a new address may carry different news
        self._result_pending = False
        self._end_confirm_pending = False
        self._resume_hold = False
        self._bridge_bound = False  # a different account starts clean
        # Re-extract address parts from THIS utterance (the correction often carries
        # the new address: "ne, skambinu dėl Dainų 5").
        self._prefill_slots_from_text(user_input)
        self._reopen_note = True

    def _last_agent_question(self) -> str | None:
        """The last thing the agent actually said — the real question the caller is
        answering (a better classifier context than the English step hint)."""
        for m in reversed(self.state.messages):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                return m["content"]
        return None

    def _classify_confirm_and_route(self, step, strat, user_input: str | None) -> bool:
        """Classifier-led routing for an asked CONFIRM step. One LLM call reads BOTH the
        answer (into a routing key) and whether it IS an answer. A confident answer
        advances the walker (overriding a brittle keyword turn-intent); anything unsure
        returns False → the keyword detector + intent gate handle it. Sensor only."""
        from .classifier import classify_step
        from .detectors import glosses as detector_glosses
        from .faults import step_options
        from .resolution import next_step_id

        detector_name = step.detector or "yes_no"
        # WHAT TO DETECT comes from the fault definition first (knowledge/faults.yaml —
        # per-step, so it can be worded precisely for THIS check), falling back to the
        # universal per-detector glosses (knowledge/detectors.yaml, code as last
        # resort). A reworded check is a file edit, not code.
        declared = step_options((self.state.resolution or {}).get("verdict"), step.id)
        glosses = detector_glosses(detector_name)
        options: dict[str, str] = {}
        for raw in step.on:
            # Some steps key `on` by the Outcome enum — str(Outcome.YES) is "Outcome.YES",
            # so take .value to get the real routing key ("yes") the classifier must return.
            key = str(getattr(raw, "value", raw))
            options[key] = (declared or {}).get(key) or glosses.get(key, key)
        question = self._last_agent_question() or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=self.config.model)
        if obs is None:
            self._trace_note("classifier", f"{step.detector or 'yes_no'}: no result → keyword")
            return False
        answered = obs.is_answer and obs.label in step.on and obs.confidence >= 0.5
        self.tracer.emit(
            "classify",
            detector=step.detector or "yes_no",
            step=step.id,
            label=obs.label,
            is_answer=obs.is_answer,
            confidence=obs.confidence,
            inconsistent=obs.internally_inconsistent,
            text=user_input,
            routed_by=("classifier" if answered else "keyword"),
        )
        if answered:
            self.state.awaiting = None
            self.state.awaiting_turns = 0
            self.state.step_confusions = 0
            self.state.last_intent = "answer"
            self._route_to(self.state.resolution, next_step_id(strat, step.id, obs.label))
            return True
        return False

    def _advance_instruct(self, r: dict, step, strat, user_input: str | None = None) -> None:
        """Advance a presented INSTRUCT/ACTION step to its goto (or the next step in order).
        Shared by the keyword path and the classifier gate. The dr_see_device VERIFY is
        engine-owned, so resolve it in the SAME turn (reflect the plug-in in the demo, then
        read the line) instead of asking a dead question."""
        from .resolution import Outcome, detect_restored, next_step_id

        self._route_to(r, step.goto or next_step_id(strat, step.id, None))
        if r.get("step") == "dr_see_device":
            self._simulate_bridge_connection()
            self._advance_see_device(r)
            return
        # Carry-through pre-answer: the utterance that completed the instruction often
        # already reports the outcome ("prisijungiau iš naujo — jau veikia"). If we just
        # landed on a restored CONFIRM and the SAME reply carries a clear YES, route it
        # now — otherwise that answer dies unheard and the caller's NEXT turn (often a
        # farewell, "Ne, ačiū") gets misread as the verify answer (observed live:
        # resolved call routed to escalate).
        new_step = strat.step(r.get("step", "")) if strat else None
        if (
            new_step is not None
            and new_step.detector == "restored"
            and detect_restored(user_input) is Outcome.YES
        ):
            self._route_to(r, next_step_id(strat, new_step.id, "yes"))

    def _classify_instruct_and_advance(self, step, strat, user_input: str | None) -> bool:
        """Classifier-led advancement for an asked INSTRUCT step: did the caller actually
        DO it, or are they still doing it / asking? A confident 'done' advances even when
        the keyword turn-intent misreads a messy done-signal as in_progress. Anything else
        returns False → the keyword intent gate decides. Sensor only."""
        from .classifier import classify_step
        from .detectors import glosses as detector_glosses

        # Meanings come from knowledge/detectors.yaml (file-editable), code fallback.
        options = detector_glosses("instruct_done")
        question = self._last_agent_question() or step.hint or ""
        obs = classify_step(question, user_input or "", options, model=self.config.model)
        if obs is None:
            return False
        done = obs.label == "done" and obs.confidence >= 0.5
        self.tracer.emit(
            "classify",
            detector="instruct_done",
            step=step.id,
            label=obs.label,
            is_answer=obs.is_answer,
            confidence=obs.confidence,
            text=user_input,
            routed_by=("classifier" if done else "keyword"),
        )
        if done:
            self.state.awaiting = None
            self.state.awaiting_turns = 0
            self.state.step_confusions = 0
            self.state.last_intent = "done"
            self._advance_instruct(self.state.resolution, step, strat, user_input)
            return True
        # Classifier VETO: the classifier RAN and did NOT say "done" (waiting OR
        # unclear) — HOLD the step unless the keyword intent is an explicit DONE
        # ("padariau", "patikrinau"), which outranks a soft classifier read (observed:
        # "Patikrinau, WiFi įjungtas" held as waiting slipped the resolve a turn).
        # Unclear included: the loose any-'answer' keyword path had advanced INSTRUCT
        # steps on garbage ("Įsitikimu, kad tai yra neturis" climbed dr_plug_pc live).
        from .resolution import INTENT_DONE, detect_turn_intent

        return detect_turn_intent(user_input) != INTENT_DONE

    def _detect_confirm(self, step, user_input: str | None):
        """Keyword FALLBACK detector for a CONFIRM reply — used when the classifier is off
        or unsure (the classifier-led path is _classify_confirm_and_route). Returns a
        routing key or None."""
        from .resolution import DETECTORS

        keyword = DETECTORS.get(step.detector or "yes_no", DETECTORS["yes_no"])
        return keyword(user_input)

    # --- Hypothesis: what we believe is wrong, and why -----------------------
    # The verdict tree decides; these just record the belief so the agent can narrate
    # the arc. Evidence comes from telemetry, never from parsing the caller.

    def _open_hypothesis(self, reason: str | None) -> None:
        """A fresh verdict = a new belief. Seeds it with what the telemetry showed."""
        if not reason:
            return
        h = self.state.hypothesis
        if h and h.get("cause") == reason and h.get("status") == "testing":
            return  # same belief, still being tested — keep its evidence
        # The ANALYSIS fuses BOTH sides (Step 2): telemetry is the first evidence,
        # the caller's anamnesis (when it broke / after what) the second — so the
        # agent reasons and narrates from the full picture ("telemetrija rodo X, o
        # klientas sako dingo po audros").
        because = [_DIAGNOSIS_LT.get(reason, reason)]
        s = self.state
        if s.anamnesis_when or s.anamnesis_trigger:
            bits = []
            if s.anamnesis_when:
                bits.append(f"dingo {s.anamnesis_when}")
            if s.anamnesis_trigger:
                bits.append(f"po: {s.anamnesis_trigger}")
            because.append("klientas sako " + ", ".join(bits))
        self.state.hypothesis = {
            "cause": reason,
            "because": because,
            "status": "testing",
            "settled_by": None,
        }

    def _note_evidence(self, text: str) -> None:
        """Add something the ENGINE learned (a telemetry read, a check outcome)."""
        h = self.state.hypothesis
        if h and text and text not in h["because"]:
            h["because"].append(text)

    def _settle_hypothesis(self, status: str, settled_by: str) -> None:
        """Close the belief: confirmed (the fix worked / the cause was proven) or
        rejected (it did not hold). Rejected ones are remembered so the engine never
        re-tries them and the agent can say what it already ruled out."""
        h = self.state.hypothesis
        if not h or h.get("status") != "testing":
            return
        h["status"] = status
        h["settled_by"] = settled_by
        if status == "rejected":
            self.state.rejected_hypotheses.append({"cause": h["cause"], "settled_by": settled_by})

    def _turn_may_advance(self, step) -> bool:
        """May the caller's turn move the walker forward?

        Only a real ANSWER or a completed action does. "Einu prie routerio" is work in
        progress, a question needs answering, confusion needs a finer explanation, and
        silence needs waiting — none of them mean the step is finished. Before this,
        every non-answer fell through to "repeat the question", which is how the agent
        ran ahead of the caller (it read a plugged-in-yet? check before they had
        plugged anything in) and repeated itself six turns running.

        Unknown is deliberately treated as an ANSWER only for CONFIRM steps, where a
        detector still has to agree — elsewhere it holds. Safe default: wait and ask."""
        from .resolution import (
            INTENT_ANSWER,
            INTENT_DONE,
            INTENT_IN_PROGRESS,
            INTENT_UNKNOWN,
            StepKind,
        )

        s = self.state
        from .resolution import INTENT_CONFUSED

        intent = s.last_intent or INTENT_UNKNOWN
        if intent in (INTENT_ANSWER, INTENT_DONE):
            s.awaiting = None
            s.awaiting_turns = 0
            s.step_confusions = 0  # they got past this one
            return True
        if intent == INTENT_CONFUSED:
            # Each "I don't follow" on the SAME step earns a smaller piece of it.
            s.step_confusions += 1
        # Still waiting on the same thing — count the turns so the agent can check in
        # ("ar pavyksta?") instead of silently re-asking the same sentence.
        s.awaiting = (
            "client_action"
            if (intent == INTENT_IN_PROGRESS or step.kind is StepKind.INSTRUCT)
            else "client_answer"
        )
        s.awaiting_turns += 1
        return False

    def _simulate_bridge_connection(self) -> None:
        """DEMO/TEST only (SIMULATE_BRIDGE=on): reflect the caller plugging a PC into the
        wall cable by making an unbound device appear on the line, so the bridge can
        VERIFY it. Off by default → production never fakes a device (the real one appears
        on its own). Best-effort: a failure just leaves the line unchanged."""
        if os.getenv("SIMULATE_BRIDGE", "off").lower() != "on":
            return
        cid = self.state.customer_id
        if not cid:
            return
        try:
            from .tools import simulate_bridge_connect

            res = simulate_bridge_connect(cid)
            self.tracer.emit("tool_call", name="simulate_bridge_connect", args={"customer_id": cid})
            if isinstance(res, dict) and res.get("success"):
                self._note_evidence("klientas prijungė įrenginį — matomas linijoje (simuliuota)")
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning(f"bridge connection sim failed: {e}")
            self._trace_note("bridge_sim", str(e))

    def _advance_see_device(self, r: dict) -> None:
        """Bridge check: after the caller plugs a computer into the wall cable, does the
        line actually SEE a device? Telemetry answers this, not the caller — binding
        blindly when the cable is in the wrong socket would fail confusingly. Seen ->
        bind; not seen after two tries -> the cable is wrong, walk it back."""
        reason = self._fresh_diagnose_reason()
        seen = reason != "no_mac_observed"  # any other verdict means a device is there
        r["device_seen"] = seen
        self._note_evidence(
            "prijungtas įrenginys matomas linijoje"
            if seen
            else "įrenginio linijoje vis dar nematyti"
        )
        if seen:
            self._goto_step(r, "dr_bind")
            return
        r["plug_retries"] = int(r.get("plug_retries", 0)) + 1
        if r["plug_retries"] >= 2:
            self._goto_step(r, "escalate")
        else:
            self._goto_step(r, "dr_pick_cable")  # wrong cable/socket — try again

    def _reject_and_rediagnose(self, r: dict) -> bool:
        """The fix ran but the line is still down: reject THIS hypothesis and look for
        another one before giving up.

        Re-reads telemetry through the normal path so state.diagnosis and the strategy
        pivot both update (the pivot skips anything already in failed_hypotheses).
        Returns True when a genuinely NEW strategy took over — the agent has a Plan B
        and says so (see `pivoted_from`); False when nothing new is left, so the caller
        escalates. Without this the FIRST failed fix ended in a ticket even when the
        telemetry had started pointing at a different fault."""
        s = self.state
        verdict = r.get("verdict")
        if verdict and verdict not in s.failed_hypotheses:
            s.failed_hypotheses.append(verdict)
        self._settle_hypothesis("rejected", "po veiksmo ryšys neatsistatė (telemetrija)")
        s.diagnosis.pop("network", None)  # let ensure_diagnosed re-read the line
        self.ensure_diagnosed()
        new = (s.resolution or {}).get("verdict")
        if new and new != verdict and new not in s.failed_hypotheses:
            s.pivoted_from = verdict  # narrate the rethink once, then clear
            return True
        return False

    def _route_to(self, r: dict, target: str) -> None:
        """Apply a routing target: the 'resolve'/'end' terminals close the case; any
        other id is a real step to advance to. Centralises terminal handling so every
        branch (including client_side -> resolve) actually closes."""
        if target == "resolve":
            self.state.case_closed = True
            self.state.closed_reason = "resolved"
            # The fix worked, so the cause we were testing was the right one — the
            # agent can now say so ("taigi dėl X ir nebuvo interneto").
            self._settle_hypothesis("confirmed", "sutvarkius problema dingo")
        elif target == "end":
            self.state.case_closed = True
            self.state.closed_reason = self.state.closed_reason or "declined"
        else:
            self._goto_step(r, target)

    def _advance_restored(self, r: dict, user_input: str | None) -> None:
        """After binding, decide from BOTH the caller's word and a fresh telemetry
        read (re-read each turn — a bind can take a minute to come up):

        - caller says it works                 -> resolved
        - caller says NO, provider side OK      -> client-side fault (Wi-Fi/device)
        - caller says NO, provider not yet OK   -> wait (reassure); after a second
                                                   denial with still-no-line, escalate
        An unclear answer stays and re-asks."""
        from .resolution import Outcome, detect_restored

        reason_now = self._fresh_diagnose_reason()
        fixed = reason_now not in self._UNRESOLVED_LINE_FAULTS
        r["telemetry_fixed"] = fixed
        if not r.get("asked"):
            return  # question not asked yet (the bind turn) — just record telemetry
        outcome = detect_restored(user_input)
        if outcome == Outcome.YES:
            self.state.case_closed = True
            self.state.closed_reason = "resolved"
            self._settle_hypothesis("confirmed", "klientas patvirtino, kad veikia")
            return
        if outcome == Outcome.NO:
            if fixed:
                # Provider side restored but the caller still has no internet — the
                # fault is inside the home. Pivot to the client-side step.
                self._goto_step(r, "client_side")
            else:
                r["restored_denials"] = int(r.get("restored_denials", 0)) + 1
                if r["restored_denials"] >= 2:
                    # The bind has not taken after waiting. Don't register yet: reject
                    # this hypothesis and see whether the telemetry now points at a
                    # different fault. Only escalate when there is no Plan B.
                    if not self._reject_and_rediagnose(r):
                        self._goto_step(r, "escalate")
                # else: stay, reassure it may take a couple of minutes (see hint)
            return
        # unclear -> stay on confirm_restored, re-ask

    def _advance_escalate(self, r: dict, step, user_input: str | None) -> None:
        """Deterministic OUTCOME for an ESCALATE step (Phase 3.11 B). Once the consent
        question was posed (asked), the caller's reply decides:
          consent  -> the ENGINE registers the ticket from STATE and closes,
          decline  -> close WITHOUT a ticket (closed_reason='declined'),
          unclear  -> hold; the narrator re-asks (stuck-guard still backstops).
        The LLM only phrases — it can no longer call create_ticket itself."""
        if not step.consent:
            return  # auto-register step — ensure_action_done handles it on arrival
        if not r.get("asked"):
            return  # consent question not posed yet — narrator asks it this turn
        from .classifier import classify_step
        from .detectors import glosses as detector_glosses
        from .resolution import detect_ticket_consent

        label = detect_ticket_consent(user_input)
        routed_by = "keyword"
        # Keyword miss -> LLM classifier (same order as CONFIRM steps: the model reads
        # messy phrasing the wordlist can't — "na jo, tebūnie", garbled STT).
        if label is None and os.getenv("CLASSIFIER", "on").lower() != "off":
            obs = classify_step(
                self._last_agent_question() or str(step.hint or ""),
                user_input or "",
                # Meanings from knowledge/detectors.yaml (file-editable), code fallback.
                detector_glosses("ticket_consent"),
                model=self.config.model,
            )
            if obs is not None and obs.is_answer and obs.confidence >= 0.5:
                label = obs.label
                routed_by = "classifier"
        self.tracer.emit(
            "classify",
            detector="ticket_consent",
            step=step.id,
            label=label,
            is_answer=label is not None,
            confidence=1.0 if label else 0.0,
            text=user_input,
            routed_by=routed_by,
        )
        if label == "yes":
            self._begin_ticket_dialogue(step)  # contacts first, then register+close
        elif label == "no":
            self.state.case_closed = True
            self.state.closed_reason = "declined"
        # unclear -> stay; the step's question is re-asked

    def _registration_claim_guard(self, content: str) -> str | None:
        """The LLM narrator CLAIMED a registration that never happened (observed
        live 2026-08-05: "Užregistravau gedimą…" at dr_recheck, ticket_id None,
        the caller hung up trusting it). Words may not outrun the engine: when a
        claim is detected with no ticket and no dialogue running, the contact
        dialogue begins NOW and its phone question is APPENDED to the reply —
        the promise becomes the process. Returns the appended text or None."""
        s = self.state
        low = (content or "").lower()
        if not any(m in low for m in ("užregistrav", "uzregistrav", "registruoju gedim")):
            return None
        if s.ticket_id or self._ticket_stage or s.case_closed or not s.customer_id:
            return None
        if s.resolution is None:
            return None
        from .identification import phrase
        from .resolution import get_strategy

        strat = get_strategy(s.resolution.get("verdict"))
        esc = strat.step("escalate") if strat else None
        s.resolution.setdefault("escalate_reason", "Sprendimas telefonu nepavyko.")
        self._begin_ticket_dialogue(esc)
        if self._ticket_stage != "phone":
            return None  # could not start (defensive) — nothing to append
        self.tracer.emit("decision", intent="ticket_dialogue", action="claim_guard")
        if self._ticket_ctx is not None:
            self._ticket_ctx["intro_done"] = True  # the claim already announced it
            self._ticket_ctx["phone_asked"] = True  # appended below — answers count
        return " " + phrase("ticket_phone")

    def _begin_ticket_dialogue(self, step) -> None:
        """Start the ticket-confirmation dialogue (2026-08-04): before ANY
        registration the agent collects the contact number (ALWAYS asked — the
        caller may be on a company/other phone, or the DB number stale) and when
        it is convenient to call. The scripted ladder asks; once complete,
        _finish_ticket_dialogue registers with the contacts on the ticket."""
        if self.state.ticket_id or self._ticket_stage:
            return  # already registered / already collecting
        self._ticket_ctx = {"step": step}
        self._ticket_stage = "phone"
        self.tracer.emit("decision", intent="ticket_dialogue", action="start")

    def _ticket_need(self) -> str:
        """Human wording of WHY the ticket is needed ("reikalingas naujas
        maršrutizatorius"), for the intro announce and the ticket itself — never
        the raw verdict key."""
        s = self.state
        cause = (s.hypothesis or {}).get("cause") or (s.resolution or {}).get("verdict") or ""
        need = _TICKET_NEED_LT.get(cause)
        if need:
            return need
        return _DIAGNOSIS_LT.get(cause, cause or "reikalinga specialisto pagalba")

    def _ticket_stage_reply(self) -> str:
        """The scripted reply for the CURRENT dialogue stage. The first phone ask
        carries the intro (phone solving is over -> registering, and WHY), so the
        caller hears the transition before the contact questions. Marks the stage
        question as ASKED — only then does the capture accept an answer — and
        speaks the retry phrasing after an unclear answer."""
        from .identification import phrase

        ctx = self._ticket_ctx if self._ticket_ctx is not None else {}
        retry = ctx.pop("ask_retry", None)
        if retry == "phone":
            return phrase("ticket_phone_retry")
        if retry == "hours":
            return phrase("ticket_hours_retry")
        if self._ticket_stage == "hours":
            ctx["hours_asked"] = True
            return phrase("ticket_hours")
        parts = []
        if not ctx.get("intro_done"):
            ctx["intro_done"] = True
            parts.append(phrase("ticket_intro", priezastis=self._ticket_need()))
        ctx["phone_asked"] = True
        parts.append(phrase("ticket_phone"))
        return " ".join(parts)

    @staticmethod
    def _fmt_phone(nr: str | None) -> str:
        """Group a dialable number for TTS ("+370 600 12353"); free text passes through."""
        raw = (nr or "").strip()
        digits = re.sub(r"[^\d+]", "", raw)
        if len(re.sub(r"\D", "", digits)) < 6 or digits != raw:
            return raw
        if digits.startswith("+370") and len(digits) == 12:
            return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
        return digits

    def _finish_ticket_dialogue(self) -> str:
        """All contacts collected (or defaulted) — register, close, announce. The
        announce repeats the number and hours back, so "kokiu numeriu?" never needs
        asking (observed live: the caller asked twice and got a goodbye)."""
        from .identification import phrase

        s = self.state
        if not s.contact_phone:
            s.contact_phone = s.caller_phone  # default: the number they call from
        if not s.contact_hours:
            s.contact_hours = "bet kada"
        step = (self._ticket_ctx or {}).get("step")
        note = (self._ticket_ctx or {}).get("note") or ""
        self._ticket_stage = None
        self._ticket_ctx = None
        self._register_ticket_from_state(step)
        s.case_closed = True
        s.closed_reason = "registered" if s.ticket_id else "declined"
        val = s.contact_hours
        val = val[:1].lower() + val[1:]  # mid-sentence: "skambinti galima bet kada"
        return phrase("ticket_done", nr=self._fmt_phone(s.contact_phone), val=val) + note

    def _register_ticket_from_state(self, step) -> None:
        """Build + create the ticket DETERMINISTICALLY from state (Phase 3.10/3.11 B):
        cause from the hypothesis/verdict, actions from this call's trace — never from
        the model's free text (which once invented an invalid ticket_type). Idempotent:
        an existing ticket is never duplicated. Best-effort: a failure is traced and the
        close still proceeds (the call record keeps the outcome)."""
        s = self.state
        if s.ticket_id or not s.customer_id:
            return
        cause = (s.hypothesis or {}).get("cause") or (s.resolution or {}).get("verdict") or ""
        gloss = _DIAGNOSIS_LT.get(cause, cause or "nenustatyta")
        details = f"Gedimas: {s.problem_type or 'internetas'} — {gloss}."
        need = _TICKET_NEED_LT.get(cause)
        if need:
            # Sentence-cased as its own sentence — "Reikalinga: reikalingas…" doubled up.
            details += f" {need[0].upper()}{need[1:]}."
        # Contacts from the ticket dialogue (2026-08-04): who to reach and when.
        if s.contact_phone or s.caller_name:
            kas = s.caller_name or "skambinęs asmuo"
            rel = f" ({s.caller_relation})" if s.caller_relation else ""
            details += f" Kontaktas: {kas}{rel}, tel. {s.contact_phone or s.caller_phone}"
            if s.contact_hours:
                details += f", skambinti: {s.contact_hours}"
            details += "."
        # The caller's anamnesis rides on the ticket — the human sees WHEN it broke
        # and after what, not just the telemetry verdict (Step 2 analysis).
        if s.anamnesis_when or s.anamnesis_trigger or s.anamnesis_raw:
            bits = []
            if s.anamnesis_when:
                bits.append(f"dingo {s.anamnesis_when}")
            if s.anamnesis_trigger:
                bits.append(f"po: {s.anamnesis_trigger}")
            details += f" Klientas: {', '.join(bits) if bits else s.anamnesis_raw}."
        if step is not None and step.id == "dr_register_router":
            details += " Laikinas tiltas per kompiuterį veikia; routeris sugedęs, reikia keisti."
        # Ledger: what the CALLER established (client-side evidence) — the human
        # taking over sees the checked physical facts, not just telemetry.
        client_bits = []
        from .evidence import CLIENT as _EV_CLIENT
        from .evidence import LABELS as _EV_LABELS
        from .evidence import VALUE_LT as _EV_VALUES

        for key, e in s.evidence.items():
            if e.get("source") == _EV_CLIENT and not e.get("conflict"):
                client_bits.append(
                    f"{_EV_LABELS.get(key, key)}: {_EV_VALUES.get(e['value'], e['value'])}"
                )
        if client_bits:
            details += f" Patikrinta su klientu: {'; '.join(client_bits)}."
        # Why it was not solved (refusal / demand / not home) — recorded on the ticket
        # so the technician knows the context (policy 2026-07-30).
        reason_note = (s.resolution or {}).get("escalate_reason")
        if reason_note:
            details += f" {reason_note}"
        # What was already TRIED and ruled out — the human taking over must not redo
        # it (after-hours philosophy 2026-08-03: the agent attempts, a person takes
        # over via the ticket with the full attempt history).
        tried = list(s.failed_hypotheses) + [
            x.get("cause") for x in s.rejected_hypotheses if x.get("cause")
        ]
        if tried:
            glosses = ", ".join(_DIAGNOSIS_LT.get(c, c) for c in dict.fromkeys(tried))
            details += f" Bandyta/atmesta: {glosses}."
        actions = self._tools_called_this_session()
        args = {
            "customer_id": s.customer_id,
            "problem_type": "technician_visit",
            "problem_description": details,
            "priority": "high",
            "notes": ("Atlikta: " + ", ".join(actions)) if actions else "",
        }
        try:
            self.tracer.emit("tool_call", name="create_ticket", args={"customer_id": s.customer_id})
            obs = execute_tool("create_ticket", args)
            self._trace_tool_result("create_ticket", obs)
            self._update_state_from_observation("create_ticket", obs)  # sets ticket_id
        except Exception as e:  # pragma: no cover - defensive
            self._trace_note("register_ticket", str(e), level="error")

    def _goto_step(self, r: dict, next_id: str) -> None:
        """Move the strategy to `next_id`. When the step actually changes, clear the
        'asked' flag so the NEXT step (e.g. a second CONFIRM like check_cable) waits
        for its OWN question to be asked before a plain yes/no can advance it."""
        if next_id != r.get("step"):
            r["asked"] = False
        r["step"] = next_id

    def _maybe_finish(self, user_input: str | None) -> None:
        """In the closing stage, decide whether to end the call. The case is already
        closed; the agent offered "ar dar kuo nors padėti?". If the caller says a
        goodbye / "no", or we have lingered a second closing turn, set is_complete so
        the transport hangs up — no endless goodbyes."""
        s = self.state
        if not s.case_closed or s.is_complete:
            return
        s.closing_turns += 1
        from .resolution import detect_farewell

        if detect_farewell(user_input) or s.closing_turns >= 2:
            s.is_complete = True

    def _maybe_close_inform(self, user_input: str | None) -> None:
        """Deterministic close for INFORM mode (mass outage, billing, or any verdict with
        NO troubleshooting strategy to walk). Once the caller has been informed and
        signals they are done — a goodbye or a plain 'no more questions' — the engine
        closes the call ITSELF and ends it on one farewell.

        Without this, closing depended on the model calling close_case, which it did not:
        the caller said goodbye repeatedly, the call stayed open, and the diagnosis node
        re-narrated the outage every turn (observed: 'kartoja gedimą')."""
        s = self.state
        if s.case_closed or not s.customer_id:
            return
        # Farewell may close the INFORM call only after the BUSINESS is done: the
        # identification ladder finished AND the news actually delivered. A garbled
        # mid-ladder "Ne, mano vardas Tomas…" matched the loose farewell heuristic and
        # HUNG UP on the caller before they ever heard the debt (observed live).
        # An OUTAGE report counts as the news told — it is delivered the moment
        # outage_reported flips (a different path than the billing script).
        if self._result_pending or self._ticket_stage or not (self._news_told or s.outage_reported):
            return
        reason = (s.diagnosis.get("network") or {}).get("reason")
        # INFORM mode: an outage was flagged, OR we identified + diagnosed but there is no
        # resolution strategy to walk (active_outage, billing_suspended, generic inform).
        # A live strategy (foreign_mac, dead-router, client_side) keeps s.resolution set
        # and is handled by the walker instead — never closed here.
        inform_mode = s.outage_reported or (s.resolution is None and bool(s.diagnosis))
        if not inform_mode:
            return
        from .resolution import detect_farewell

        if detect_farewell(user_input):
            s.case_closed = True
            s.closed_reason = (
                "outage" if (s.outage_reported or reason == "active_outage") else "inform"
            )
            s.is_complete = True  # caller already said goodbye — end on ONE farewell
            # Observability: the close moment was invisible in the trace (this made a
            # stuck-close analysis needlessly hard) — record it.
            self.tracer.emit("decision", intent="inform_close", action="close", to=s.closed_reason)

    def _mark_step_presented(self) -> None:
        """After the agent replies while on a strategy step, record that the step's
        message (a CONFIRM question, an INSTRUCT instruction, or the ACTION announce)
        has now been presented — so the caller's NEXT reply advances the walker."""
        self.state.pivoted_from = None  # the rethink has now been said — say it once
        s = self.state
        # Identification ladder bookkeeping: while the caller-intro question is owed,
        # the strategy step's question was NOT asked this reply — do not mark it. Once
        # the caller introduced themselves and the RESULT was narrated, the deferral
        # closes (inform news counted as told).
        if s.customer_id and self._result_pending:
            if not s.caller_name:
                return  # the reply asked WHO is calling — nothing else was presented
            self._result_pending = False
            if s.resolution is None:
                self._news_told = True
        r = self.state.resolution
        if not r:
            return
        from .resolution import StepKind, get_strategy

        strat = get_strategy(r.get("verdict"))
        step = strat.step(r.get("step", "")) if strat else None
        if step is not None and step.kind in (
            StepKind.CONFIRM,
            StepKind.INSTRUCT,
            StepKind.ACTION,
            StepKind.ESCALATE,  # the consent question ("ar tinka?") — Phase 3.11 B
        ):
            r["asked"] = True

    def _augment_resolve_result(self, observation: str) -> str:
        """Identification just landed — diagnose in the SAME turn.

        Otherwise the identification turn has nothing real left to say (the address is
        already confirmed) and the model fills the gap: it invents "nėra žinomų
        gedimų", asks "kokie įrenginiai prijungti?", and a debtor only hears about the
        debt a turn later — or the caller goes quiet and the call stalls before any
        diagnosis. Running it here lets ONE reply confirm the address and deliver the
        finding."""
        try:
            obs = json.loads(observation)
        except (TypeError, ValueError):
            return observation
        if not obs.get("success") or not self.state.customer_id:
            return observation
        if not self.ensure_diagnosed():
            return observation
        # The address was JUST confirmed (that is what triggered this diagnose) — the
        # lookup hint still says "patvirtink adresą klientui", and the narrator obeying
        # it re-asked the ADDRESS instead of moving on. Neutralize the stale hint.
        obs["hint"] = "Adresas JAU patvirtintas — nebeklausk adreso."
        # Arc v3 (2026-07-31, Andrius' variant 1): identification is SEPARATE from
        # diagnosis — the engine has already diagnosed silently (state-only), and this
        # ONE reply narrates the check announce AND its real result in sequence:
        # "Patikrinsiu būseną šiuo adresu… Patikrinau: [rezultatas]." No caller-ack
        # turn (a told-to-wait caller stays silent -> dead air), and no deferred-finding
        # vacuum for the model to hallucinate into (observed: it invented a router
        # story for a debtor). When async telemetry lands (Phase 5), the announce and
        # the result naturally split into two real turns.
        obs["message"] = (obs.get("message", "") or "").strip() + self._result_narration_tail()
        return json.dumps(obs, ensure_ascii=False)

    def _result_narration_tail(self) -> str:
        """The narration directive once the identity has committed and the silent
        diagnose ran. Identification LADDER (2026-07-31): if the caller-intro question
        is still owed (WHO is calling — name + relation, for the record), ask THAT
        first and hold the result one turn (_result_pending); otherwise narrate the
        check announce + the REAL result in this one reply (arc v3)."""
        from .identification import ask_caller, caller_question

        if ask_caller() and not self.state.caller_name:
            self._result_pending = True
            return (
                " Identifikacijos pabaiga: patikra atlikta TYLIAI, bet rezultato dar "
                f"NESAKYK. Šiame atsakyme TIK: „{caller_question()}“ (galima trumpai "
                "patvirtinti adresą prieš klausimą). Jokio rezultato, jokių instrukcijų."
            )
        d = self.state.diagnosis.get("network") or {}
        gloss = _DIAGNOSIS_LT.get(d.get("reason"), d.get("reason") or "—")
        if self.state.resolution:
            return (
                f" Patikra atlikta. REZULTATAS: {gloss}. Šiame VIENAME atsakyme, šia "
                "tvarka: (1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) trumpai "
                "pasakyk rezultatą ir kas tai greičiausiai yra, (3) užduok ŠIO ŽINGSNIO "
                "klausimą (jis atlieka „ar darome?“ vaidmenį). NEkartok adreso klausimo, "
                "NEkartok anamnezės klausimo, jokių instrukcijų sąrašo — vienas klausimas."
            )
        self._news_told = True  # the news goes out in THIS reply — never repeat it
        return (
            f" Patikra atlikta. ŽINIA: {gloss}. Šiame VIENAME atsakyme, šia tvarka: "
            "(1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) pasakyk žinią "
            "VIENĄ kartą trumpai (jei skola — BŪTINAI pridėk: „apmokėjus sąskaitą, "
            "paslauga bus įjungta“), (3) paklausk „Ar dar kuo galiu padėti?“. "
            "NEkartok adreso klausimo ir daugiau šios žinios NEBEKARTOK."
        )

    def _augment_tool_result(self, name: str, observation: str) -> str:
        """Deterministic post-action chaining + telemetry verification (B6 strategy).

        update_mac ALONE does not restore service — the port must be reset and the
        line re-checked. Rather than trust the model to remember the whole sequence
        (observed: it bound nothing and closed on the caller's word), the engine
        chains it: after a successful update_mac it runs reset_port and re-reads the
        telemetry, and hands the model a VERIFIED outcome to narrate (what the
        provider side actually shows, not what the caller claims)."""
        if name == "resolve_address":
            return self._augment_resolve_result(observation)
        if name != "update_mac":
            return observation
        try:
            obs = json.loads(observation)
        except (TypeError, ValueError):
            return observation
        if not obs.get("success"):
            return observation  # nothing bound (e.g. no_observed_mac) — leave as is
        cid = self.state.customer_id
        try:
            rp = json.loads(execute_tool("reset_port", {"customer_id": cid}))
            self.tracer.emit("tool_call", name="reset_port", args={"customer_id": cid})
            obs["auto_reset_port"] = bool(rp.get("success"))
        except Exception:  # pragma: no cover - best-effort
            obs["auto_reset_port"] = None
        reason_now = self._fresh_diagnose_reason()
        fixed = reason_now not in self._UNRESOLVED_LINE_FAULTS
        obs["telemetry_after"] = reason_now
        obs["fixed"] = fixed
        gloss = _DIAGNOSIS_LT.get(reason_now, reason_now or "—")

        # Do NOT close or advance here. The bind was announced THIS turn; the walker
        # advances bind_mac -> confirm_restored on the caller's next reply, where we
        # ASK them and re-read telemetry before deciding resolve / client-side /
        # escalate (_advance_restored). Just record the telemetry reading.
        r = self.state.resolution
        if r is not None:
            r["telemetry_fixed"] = fixed
        obs["message"] = (
            obs.get("message", "") or ""
        ).strip() + f" Portas perkrautas. Telemetrija dabar: {gloss}."
        return json.dumps(obs, ensure_ascii=False)

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
        # check_outages must be street-specific. A city-only query returns OTHER
        # streets' outages, which the model then misattributes to the caller
        # (observed). Require a street (area="Miestas, Gatvė") OR a customer_id —
        # the house/apartment is NOT required (street-level check is valid pre-house).
        if name == "check_outages":
            area = (args.get("area") or "").strip()
            if area and "," not in area and not args.get("customer_id"):
                return json.dumps(
                    {
                        "success": False,
                        "error": "city_only",
                        "message": (
                            "check_outages reikalauja gatvės: perduok area='Miestas, "
                            "Gatvė' (ne vien miestą) arba customer_id. Tik-miesto "
                            "patikra grąžina kitų gatvių gedimus."
                        ),
                    },
                    ensure_ascii=False,
                )
            return None

        # close_case: reason-specific backstop so an over-eager model can't end the
        # call prematurely. "resolved" needs an identified customer; "outage" needs
        # an outage to have actually been reported.
        if name == "close_case":
            reason = args.get("reason", "resolved")
            if reason == "resolved":
                if not self.state.customer_id:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "not_identified",
                            "message": "Negalima uždaryti kaip 'resolved' neidentifikavus kliento.",
                        },
                        ensure_ascii=False,
                    )
                # Verify-gate: telemetry is the source of truth. If a fresh
                # diagnose still shows the line fault, the fix has NOT taken —
                # block "resolved" so the agent can't close on the caller's word
                # (observed: B6 closed as resolved without ever binding the MAC).
                reason_now = self._fresh_diagnose_reason()
                if reason_now in self._UNRESOLVED_LINE_FAULTS:
                    gloss = _DIAGNOSIS_LT.get(reason_now, reason_now)
                    return json.dumps(
                        {
                            "success": False,
                            "error": "not_fixed",
                            "message": (
                                f"Telemetrija dar rodo gedimą ({gloss}) — dar NEsutvarkyta, "
                                "neuždaryk kaip 'resolved'. Atlik reikiamą veiksmą (pvz. "
                                "update_mac + reset_port) ir per-tikrink diagnostiką."
                            ),
                        },
                        ensure_ascii=False,
                    )
            if reason == "outage" and not self.state.outage_reported:
                return json.dumps(
                    {
                        "success": False,
                        "error": "no_outage",
                        "message": (
                            "close_case(reason='outage') leidžiama tik po to, kai "
                            "check_outages patvirtino aktyvų gedimą."
                        ),
                    },
                    ensure_ascii=False,
                )
            return None

        if name not in self._GATED_TOOLS:
            return None
        if not self.state.customer_id:
            return json.dumps(
                {
                    "success": False,
                    "error": "not_identified",
                    "message": (
                        "Klientas dar neidentifikuotas. Pirma surask ir patvirtink "
                        "adresą (resolve_address) — tik tada galima diagnozė ar veiksmai."
                    ),
                }
            )
        cid = args.get("customer_id")
        if cid and cid != self.state.customer_id:
            return json.dumps(
                {
                    "success": False,
                    "error": "id_mismatch",
                    "message": (
                        f"customer_id turi būti identifikuoto kliento: "
                        f"{self.state.customer_id}. Nenaudok kito ar spėto id."
                    ),
                }
            )
        return None

    def _update_state_from_observation(self, action: str, observation: str):
        """Update agent state based on tool observation."""
        try:
            obs_data = json.loads(observation)

            # Fold the per-level address resolution into the durable slots on
            # EVERY resolve_address call (success or not) — what the caller said
            # accumulates as structured memory, protected from low-confidence
            # overwrites (slots.Slot.propose).
            if action == "resolve_address" and isinstance(obs_data.get("resolution"), dict):
                self.state.profile.update_from_resolution(obs_data["resolution"])

            if action in ("find_customer", "resolve_address") and obs_data.get("success"):
                # resolve_address nests the normalized profile under `customer`;
                # find_customer returns it flat. Same shape either way.
                profile = obs_data.get("customer") or obs_data
                addresses = profile.get("addresses") or []
                # Normalized addresses carry `full_address` (primary first
                # when available).
                primary = next(
                    (a for a in addresses if a.get("is_primary")),
                    addresses[0] if addresses else {},
                )
                if profile.get("customer_id"):
                    self.state.set_customer_info(
                        customer_id=profile.get("customer_id"),
                        name=profile.get("name"),
                        address=primary.get("full_address"),
                    )

            elif action == "create_ticket" and obs_data.get("success"):
                self.state.ticket_id = obs_data.get("ticket_id")
                # Inside a resolution strategy (escalate step), the fault is now
                # registered — close the case so create_ticket is withdrawn and the
                # model narrates the close instead of re-registering in a loop.
                if self.state.resolution and not self.state.case_closed:
                    self.state.case_closed = True
                    self.state.closed_reason = "registered"

            # Diagnostic findings -> case state under their DOMAIN, so the agent
            # reconciles them with the customer and never loses / re-runs them, and
            # new fault families attach additively (§12.1).
            if action == "diagnose_connection" and isinstance(obs_data.get("verdict"), dict):
                v = obs_data["verdict"]
                self.state.diagnosis["network"] = {
                    "group": v.get("group"),
                    "side": v.get("side"),
                    "action": v.get("action"),
                    "reason": v.get("reason"),
                    "signals": v.get("signals"),
                }
                # Ledger: telemetry facts are ground truth — every (re)diagnose
                # lands on the evidence with full history (a re-check after a fix
                # OVERWRITES the value; the caller's words never do).
                from .evidence import TELEMETRY, set_fact

                turn = self.state.turn_count
                if v.get("reason"):
                    set_fact(self.state.evidence, "verdict", v["reason"], TELEMETRY, turn)
                if v.get("side"):
                    set_fact(self.state.evidence, "side", v["side"], TELEMETRY, turn)
                # A verdict IS a hypothesis — record what we now believe and why, so
                # the agent can say it aloud and later report how it settled.
                self._open_hypothesis(v.get("reason"))
                # Activate / re-evaluate the resolution strategy for this verdict
                # (dynamic pivot: a re-diagnose with a different verdict switches
                # strategy). None = generic inform/instruct flow.
                from .resolution import get_strategy

                strat = get_strategy(v.get("reason"))
                # Never pivot back into a hypothesis the telemetry already disproved —
                # that is how a re-diagnose after a failed fix would loop forever.
                if strat is not None and strat.verdict not in self.state.failed_hypotheses:
                    prev = (self.state.resolution or {}).get("verdict")
                    if prev != strat.verdict:  # new or pivoted
                        self.state.resolution = {
                            "verdict": strat.verdict,
                            "step": strat.steps[0].id,
                        }

            # An active outage for the caller's street -> restricted mode (NOT a
            # close): the caller still asks "when fixed? / compensation?", so the
            # agent stays in a tool-having node but stops diagnosing (facts block).
            # By the gate, a returned `affected` here is already street-specific.
            if action == "check_outages" and obs_data.get("affected"):
                self.state.outage_reported = True

            # close_case signal -> flip the router to the closing stage. The model
            # owns WHEN (it read the caller's confirmation); the gate already
            # backstopped premature/unfounded closes.
            if action == "close_case" and obs_data.get("case_closed"):
                self.state.case_closed = True
                self.state.closed_reason = obs_data.get("reason")

        except json.JSONDecodeError:
            pass

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
        phone = self.state.caller_phone
        if not phone or phone == "unknown":
            return
        self.state.preflight_done = True
        try:
            result = json.loads(execute_tool("find_customer", {"phone": phone}))
        except Exception:
            return
        if not result.get("success"):
            self.tracer.emit("preflight", found=False)
            return
        addresses = result.get("addresses") or []
        primary = next(
            (a for a in addresses if a.get("is_primary")),
            addresses[0] if addresses else {},
        )
        self.state.phone_candidate = {
            "customer_id": result.get("customer_id"),
            "name": result.get("name"),
            "address": primary.get("full_address"),
            # Structured parts for the phone cross-check: if the caller names this
            # street, offer the full address to confirm instead of making them
            # dictate the house/apartment (spoken numbers are STT-fragile).
            "city": primary.get("city"),
            "street": primary.get("street"),
            "house": primary.get("house_number"),
            "apartment": primary.get("apartment_number"),
        }
        self.tracer.emit("preflight", found=True, customer_id=result.get("customer_id"))

        # Proactive mass-outage awareness (roadmap 6b): if this caller's street
        # has an active outage, remember it so the FIRST reply can inform right
        # away — no full identification needed (everyone at that street is down).
        try:
            outage = json.loads(
                execute_tool("check_outages", {"customer_id": result.get("customer_id")})
            )
        except Exception:
            return
        if outage.get("affected") and outage.get("active_outages"):
            first = outage["active_outages"][0]
            eta = first.get("estimated_resolution") or ""
            self.state.preflight_outage = {
                "street": first.get("street"),
                "eta": eta[11:16] if len(eta) >= 16 else eta,  # HH:MM, voice-friendly
                "description": first.get("description"),
            }
            self.tracer.emit("preflight_outage", street=first.get("street"))

    def _prefill_slots_from_text(self, text: str) -> None:
        """Deterministic NLU Track A: extract the address from the caller's turn and
        propose it into the slots BEFORE the LLM runs (docs/pokalbio_variklis.md §4).

        The reading is the high-confidence floor — registry-validated street +
        normalized numbers — so the slots get a reliable source independent of the
        LLM. Proposed as HEARD; resolve_address upgrades a confirmed hit to
        RESOLVED. Best-effort: any failure (DB, import) silently no-ops the turn.
        """
        # Raw utterance buffer: keep every caller turn verbatim so nothing is lost
        # when VAD/STT splits an utterance into fragments. Feeds the LLM
        # reconciliation fact when the deterministic slots stall (see
        # _state_facts_block), and the future async silent re-processing.
        if text and text.strip():
            self.state.heard_utterances.append(text.strip())

        # Problem classification (R1) — independent of the registry/DB, so it runs
        # even if address extraction fails. A revisable hypothesis: a clearer later
        # statement overrides (docs/pokalbio_variklis.md §12.2).
        try:
            from .nlu import classify_problem, extract_symptoms

            problem = classify_problem(text)
            if problem:
                self.state.problem_type = problem
            # Revisable: a clearer later mention overrides an earlier reading.
            self.state.symptoms.update(extract_symptoms(text))
        except Exception:  # pragma: no cover - best-effort
            pass

        # Address-evidence gate: only scan the turn for an address when it plausibly
        # CONTAINS one — a digit or an address word in the utterance, or the agent just
        # asked for the address. Without this, fuzzy street matching read an ADDRESS out
        # of the anamnesis answer ("po AUDROS" -> "Aušros g.") and the bogus street slot
        # blocked the phone-address offer, derailing identification (observed).
        low = (text or "").lower()
        has_addr_evidence = any(ch.isdigit() for ch in low) or any(
            w in low for w in ("gatv", " g.", "prospekt", "alėj", "aikšt", "kaim", "adres", "but")
        )
        if not has_addr_evidence:
            q = (self._last_agent_question() or "").lower()
            asked_address = any(w in q for w in ("adres", "gatv", "namo", "numer", "but"))
            if not asked_address:
                return  # no address in sight — do not fuzzy-match one into the slots
        try:
            from .nlu import extract_address, load_registry
            from .slots import SlotStatus
            from .tools import get_db

            if self._registry is None:
                self._registry = load_registry(get_db())
            streets, localities = self._registry
            reading = extract_address(text, streets, localities)
        except Exception:  # pragma: no cover - best-effort, never break a turn
            logger.debug("NLU prefill failed", exc_info=True)
            return

        p = self.state.profile
        conf = reading.street_confidence or 0.6
        if reading.city:
            p.city.propose(reading.city, conf, SlotStatus.HEARD)
        if reading.street:
            p.street.propose(reading.street, conf, SlotStatus.HEARD)
        if reading.house:
            p.house.propose(reading.house, conf, SlotStatus.HEARD)
        if reading.apartment:
            p.apartment.propose(reading.apartment, conf, SlotStatus.HEARD)

        # If the caller names a DIFFERENT street than the pre-flight outage was
        # for, that outage is not theirs — drop it so its proactive instruction
        # stops polluting the rest of the call (observed: the agent kept
        # apologising and re-mentioning the outage after the caller switched
        # streets).
        if (
            reading.street
            and self.state.preflight_outage
            and reading.street != self.state.preflight_outage.get("street")
        ):
            self.state.preflight_outage = None

        self.tracer.emit(
            "nlu",
            problem=self.state.problem_type,
            city=reading.city,
            street=reading.street,
            house=reading.house,
            apartment=reading.apartment,
            confidence=round(reading.street_confidence, 2),
        )

        # DB-ground everything heard so far (any order, across fragments).
        self._revalidate_accumulated_address()

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
        self._db_address_note = None
        s = self.state
        if s.customer_id or not s.profile.street.value:
            return
        p = s.profile
        args: dict[str, str] = {"street": p.street.value}
        if p.city.value:
            args["city"] = p.city.value
        if p.house.value:
            args["house_number"] = p.house.value
        if p.apartment.value:
            args["apartment_number"] = p.apartment.value
        try:
            res = json.loads(execute_tool("resolve_address", args))
        except Exception:  # pragma: no cover - best-effort, never break a turn
            return
        hint = res.get("hint")
        if hint:
            self._db_address_note = (
                f"- DB CHECK (everything heard so far → {args}): {hint} "
                "Act on THIS (the DB), not on the last thing you misheard; if it is a "
                "match, confirm that exact address; if a part is missing/unclear, ask "
                "only for it. Do NOT read out a list of street names for the caller to "
                "pick from — if the street is unclear, ask them to repeat it."
            )

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

            s.resolution.setdefault("escalate_reason", "Pokalbis nutrūko — klientas padėjo ragelį.")
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
        self.state.messages.append(self._assistant_tool_message(message))
        executed = []
        for tc in message.tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning(f"[AGENT] Bad tool arguments for {name}: {raw_args!r}")
                self._trace_note("tool_args", f"{name}: bad JSON args {raw_args!r}")
                args = {}

            logger.info(f"[AGENT] Tool call: {name}")
            self.tracer.emit("tool_call", name=name, args=args)

            gate = self._gate_tool(name, args)
            if gate is not None:
                observation, tool_ms = gate, 0
                self._update_state_from_observation(name, observation)
            else:
                _t = time.perf_counter()
                observation = execute_tool(name, args)
                tool_ms = round((time.perf_counter() - _t) * 1000.0)
                # Commit state BEFORE augmenting: resolve_address sets customer_id
                # here, and the augment then diagnoses in the same turn (it read a
                # not-yet-committed id and skipped, so the strategy never activated —
                # the whole dead-router walk fell back to free-form LLM). _update reads
                # only raw tool fields, never the ones augment adds, so the order is safe.
                self._update_state_from_observation(name, observation)
                observation = self._augment_tool_result(name, observation)

            self.state.messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": observation}
            )
            self._trace_tool_result(name, observation, tool_ms)
            self.state.add_observation(observation)
            executed.append({"name": name, "arguments": args, "observation": observation})
        return executed

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

        self.state.last_heard = (user_input or "").strip()
        from .resolution import detect_turn_intent

        self.state.last_intent = detect_turn_intent(user_input)
        self._maybe_raise_clarity(user_input)
        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            self._prefill_slots_from_text(user_input)
            self._pre_turn_guards(user_input)

        # Deterministic backstop (before the LLM, so it works with streaming) once a
        # genuine repeat loop has escalated.
        backstop = self._stuck_backstop()
        if backstop is not None:
            yield self._apply_backstop(backstop)
            return

        # Scripted identification-ladder reply (engine-composed, LLM skipped) — the
        # mechanical turns only; off-script turns fall through to the LLM.
        scripted = self._identification_scripted_reply(user_input)
        if scripted is not None:
            yield self._emit_scripted_reply(scripted)
            return

        max_calls = self.config.max_tool_calls_per_response
        tool_rounds = 0
        while tool_rounds < max_calls:
            self.state.turn_count += 1
            if self.state.turn_count > self.state.max_turns:
                yield self.config.max_turns_message
                return

            messages = self._build_messages(user_input)
            if user_input:
                self.state.messages.append({"role": "user", "content": user_input})
                user_input = None

            try:
                message = yield from stream_tool_completion(
                    messages=messages,
                    tools=self._scoped_tools_schema(),
                    tool_choice="auto",
                    model=self.config.model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
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
        s = self.state
        if s.case_closed:
            return None
        from .identification import caller_question, offer_phone_address, phrase
        from .resolution import is_real_question

        # Ticket-confirmation dialogue: contacts before every registration. An
        # off-script question falls to the ticket node's LLM (facts carry the
        # pending stage question to re-ask); the mechanical turns stay scripted.
        if self._ticket_stage in ("phone", "hours"):
            if self._ticket_offscript:
                return None
            return self._ticket_stage_reply()
        if self._ticket_stage == "done":
            return self._finish_ticket_dialogue()
        if self._ticket_stage == "cancelled":
            self._ticket_stage = None
            self._ticket_ctx = None
            s.case_closed = True
            s.closed_reason = "declined"
            s.is_complete = True
            return "Gerai — gedimo neregistruoju. " + phrase("goodbye")
        # Ledger conflict clarify (ONE question, engine-composed): "sakėte X,
        # dabar Y — kaip yra iš tiesų?" — the next answer settles the fact.
        if self._evidence_conflict:
            from .evidence import LABELS, VALUE_LT

            key, old, new = self._evidence_conflict
            self._evidence_conflict = None
            self._evidence_conflict_asked = key
            return phrase(
                "evidence_conflict",
                tema=LABELS.get(key, key),
                a=VALUE_LT.get(old, old),
                b=VALUE_LT.get(new, new),
            )
        # Farewell-mid-process clarify (any stage): ONE deterministic confirm question.
        if self._end_confirm_pending:
            return phrase("confirm_end")
        if user_input and is_real_question(user_input):
            return None  # off-script — the LLM answers; guards kept the ladder state
        # INTAKE (not yet identified): the anamnesis question and the address
        # offer/ask are mechanical too — the LLM repeated the anamnesis and slid the
        # whole ladder by a turn (observed in eval).
        if not s.customer_id:
            p = s.profile
            has_addr = bool(p.street.value or p.house.value)
            if s.problem_type and not s.anamnesis_asked and not s.preflight_outage and not has_addr:
                s.anamnesis_asked = True
                return phrase("anamnesis_question")
            if s.anamnesis_asked and s.anamnesis_raw is None and user_input and not has_addr:
                s.anamnesis_raw = user_input.strip()[:200]
                from .nlu import extract_anamnesis

                read = extract_anamnesis(s.anamnesis_raw)
                s.anamnesis_when = read.get("when")
                s.anamnesis_trigger = read.get("trigger")
                self.tracer.emit(
                    "anamnesis",
                    text=s.anamnesis_raw,
                    when=s.anamnesis_when,
                    trigger=s.anamnesis_trigger,
                )
                c = s.phone_candidate
                if offer_phone_address() and c and c.get("street") and not s.preflight_outage:
                    flat = f", butas {c['apartment']}" if c.get("apartment") else ""
                    return phrase("address_offer", adresas=f"{c['street']} {c.get('house')}{flat}")
                return phrase("address_ask")
            return None
        # WRAP-UP after the news (inform mode): the business is DONE — any further
        # turn that is not a question/wants-more wraps up DETERMINISTICALLY. Garbled
        # goodbyes ("Nusigaro" = "viso gero") had the model loop "nesupratau,
        # pakartokite" after a delivered debt notice (observed live: the caller could
        # not end the call).
        if (
            s.resolution is None
            and (self._news_told or s.outage_reported)
            and not self._result_pending
        ):
            low = (user_input or "").lower()
            wants_more = any(
                m in low
                for m in (
                    "klausim",
                    "palauk",
                    "dar ",
                    "noriu",
                    "minut",
                    "sekund",
                    "o kod",
                    "o kiek",
                )
            )
            if wants_more:
                return None  # they want something else — the LLM handles it
            s.case_closed = True
            s.closed_reason = "outage" if s.outage_reported else "inform"
            s.is_complete = True
            self.tracer.emit("decision", intent="wrap_up", action="close", to=s.closed_reason)
            return phrase("goodbye")
        if not self._result_pending:
            return None
        if not s.caller_name:
            # The caller-intro question turn (with the address echo on a fresh commit).
            parts = []
            if self._just_identified and s.customer_address:
                parts.append(phrase("echo_address", adresas=s.customer_address))
            self._just_identified = False
            parts.append(caller_question())
            return " ".join(p for p in parts if p)
        # The caller introduced themselves — deliver the deferred result. INFORM
        # verdicts are fully mechanical; a strategy result (finding + step question)
        # stays with the LLM (returns None; the REZULTATO facts directive drives it).
        if s.resolution is not None:
            return None
        d = s.diagnosis.get("network") or {}
        reason = d.get("reason")
        zinia = _DIAGNOSIS_LT.get(reason, reason or "")
        if not zinia:
            return None
        zinia = zinia[0].upper() + zinia[1:]  # sentence-cased after "…iki jūsų buto."
        bits = [phrase("thanks"), phrase("check_result", zinia=zinia + ".")]
        if reason == "billing_suspended":
            bits.append(phrase("billing_extra"))
        # Outage news carries the ETA when the preflight knows it.
        if reason == "active_outage" and (s.preflight_outage or {}).get("eta"):
            bits.append(f"Numatomas atstatymas iki {s.preflight_outage['eta']}.")
        bits.append(phrase("anything_else"))
        self._result_pending = False
        self._news_told = True
        return " ".join(b for b in bits if b)

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
        """Catch-all hang-up: if the agent JUST said a terminal goodbye — on ANY path
        (resolved, registered, declined, or the stuck backstop) — end the call so the
        transport stops instead of looping the goodbye. Covers the cases the
        case_closed/closing flow misses (e.g. the model says 'geros dienos' on a stuck
        turn without close_case ever firing)."""
        if self.state.is_complete or not text:
            return
        low = text.lower()
        if any(m in low for m in _GOODBYE_MARKERS):
            self.state.is_complete = True

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
