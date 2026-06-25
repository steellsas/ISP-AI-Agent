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

# Short Lithuanian gloss for each verdict reason, surfaced in the case-state facts
# block so the agent can reconcile the finding with what the customer says.
_DIAGNOSIS_LT = {
    "billing_suspended": "paslauga sustabdyta dėl neapmokėtos sąskaitos",
    "active_outage": "rajone registruota masinė avarija",
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

        # Per-node scoping (LangGraph step 3.2): a graph node may restrict the
        # tools exposed to the model and add a focused prompt. None = unrestricted
        # (the legacy single-agent behaviour).
        self._active_tool_names: frozenset[str] | None = None
        self._node_prompt: str | None = None

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

        return messages

    def _scoped_tools_schema(self) -> list:
        """The tool schema for the current node — all tools, or only the subset a
        graph node restricted the model to (self._active_tool_names)."""
        if self._active_tool_names is None:
            return self.tools_schema
        return [
            t
            for t in self.tools_schema
            if t.get("function", {}).get("name") in self._active_tool_names
        ]

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
        # Diagnostic findings (case state), per domain: durable current truth, so
        # the agent reconciles them with the caller and never re-runs / loses them.
        # Only active domains are surfaced (lean — history lives in the trace, §12.7).
        for domain, d in s.diagnosis.items():
            gloss = _DIAGNOSIS_LT.get(d.get("reason"), d.get("reason") or "—")
            facts.append(
                f"- DIAGNOSTIKA [{domain}] ({d.get('group')}, pusė={d.get('side')}): "
                f"{gloss}. Remkis šiais radiniais; NEdiagnozuok iš naujo ir jų "
                "neprarask. Jei klientas sako kitaip nei rodo diagnostika, švelniai "
                "sutaikink."
            )
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
        # Pre-flight phone candidate: known but UNCONFIRMED until the caller
        # agrees the offered address is theirs (anchor rule). Only relevant
        # before a customer has been confirmed.
        if not s.customer_id and s.phone_candidate and s.phone_candidate.get("address"):
            cand = s.phone_candidate
            facts.append(
                f"- PHONE CANDIDATE (unconfirmed): the caller's number is registered to "
                f"address {cand['address']} (customer {cand['customer_id']}). Your FIRST "
                f"reply should offer THIS address for confirmation; if the caller agrees, "
                f"use customer_id {cand['customer_id']} for diagnosis. If they state a "
                f"different address, ignore this candidate."
            )
        elif s.preflight_done and not s.customer_id and s.caller_phone not in (None, "", "unknown"):
            # Pre-flight ran and found NO account for this number. Make the absence
            # explicit so the model cannot invent a "skambinate iš numerio..."
            # address out of thin air (observed hallucination).
            facts.append(
                "- NO phone account is on file for this caller's number. You do NOT "
                "know their address — NEVER say 'skambinate iš numerio, registruoto "
                "adresu ...' and never invent one. Ask for the address."
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
        }
        self.tracer.emit("preflight", found=True, customer_id=result.get("customer_id"))

    def _prefill_slots_from_text(self, text: str) -> None:
        """Deterministic NLU Track A: extract the address from the caller's turn and
        propose it into the slots BEFORE the LLM runs (docs/pokalbio_variklis.md §4).

        The reading is the high-confidence floor — registry-validated street +
        normalized numbers — so the slots get a reliable source independent of the
        LLM. Proposed as HEARD; resolve_address upgrades a confirmed hit to
        RESOLVED. Best-effort: any failure (DB, import) silently no-ops the turn.
        """
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

        self.tracer.emit(
            "nlu",
            problem=self.state.problem_type,
            city=reading.city,
            street=reading.street,
            house=reading.house,
            apartment=reading.apartment,
            confidence=round(reading.street_confidence, 2),
        )

    def end_session(self, outcome: str | None = None) -> None:
        """Emit session_end once (idempotent). Call when the conversation ends."""
        if self._session_ended:
            return
        self._session_ended = True
        self.tracer.emit(
            "session_end",
            outcome=outcome,
            customer_id=self.state.customer_id,
            ticket_id=self.state.ticket_id,
            turn_count=self.state.turn_count,
            llm_calls=self.llm_stats.total_calls,
            total_tokens=self.llm_stats.total_tokens,
            total_cost=round(self.llm_stats.total_cost, 5),
        )
        # Write a human-readable transcript next to the JSONL, if supported.
        export = getattr(self.tracer, "export_txt", None)
        if callable(export):
            export()

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
                args = {}

            logger.info(f"[AGENT] Tool call: {name}")
            self.tracer.emit("tool_call", name=name, args=args)

            gate = self._gate_tool(name, args)
            if gate is not None:
                observation, tool_ms = gate, 0
            else:
                _t = time.perf_counter()
                observation = execute_tool(name, args)
                tool_ms = round((time.perf_counter() - _t) * 1000.0)

            self.state.messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": observation}
            )
            self._trace_tool_result(name, observation, tool_ms)
            self._update_state_from_observation(name, observation)
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

        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            self._prefill_slots_from_text(user_input)

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
            # to history and emit the trace (no extra yield).
            self.state.messages.append({"role": "assistant", "content": content})
            self._emit_case()
            self.tracer.emit("agent_reply", text=content)
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

        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            # Deterministic NLU prefill (Track A) before the LLM sees the turn.
            self._prefill_slots_from_text(user_input)

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
        self.tracer.emit(
            "case",
            problem=s.problem_type,
            customer_id=s.customer_id,
            address=s.customer_address,
            symptoms=(", ".join(f"{k}={v}" for k, v in s.symptoms.items()) or None),
            diagnosis=diag,
        )

    def _reply(self, text: str) -> str:
        """Emit the customer-facing reply to the trace and return it."""
        self._emit_case()
        self.tracer.emit("agent_reply", text=text)
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
