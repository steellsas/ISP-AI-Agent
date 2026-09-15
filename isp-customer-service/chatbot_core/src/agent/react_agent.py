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

import logging
from contextlib import suppress
from functools import lru_cache

# LLM client
from src.services.llm.client import (
    get_last_call_stats,
    stream_tool_completion,
)

from .contract.locale import phrase
from .dialog_utils import is_question, progress_key, similar
from .faults import role_of, verdict_flag
from .graph_v2.state import GraphState
from .prompts import load_system_prompt
from .runtime import AgentRuntime
from .trace import emit_case, tools_called_this_session, trace_note

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


@lru_cache(maxsize=16)
def system_prompt_for(caller_phone: str, language: str) -> str:
    """The byte-stable system prompt for a call (cacheable prefix)."""
    return load_system_prompt(
        tools_description=get_tools_description(),
        caller_phone=caller_phone,
        language=language,
    )


class ReactAgent:
    """
    ReAct pattern agent for ISP customer support.

    Attributes:
        state: Current conversation state
        config: Agent configuration
        system_prompt: Formatted system prompt
    """

    def __init__(self, state: GraphState, runtime: AgentRuntime):
        """The narrator loop for one node run: `state` is the node's working copy,
        `runtime` the call's dependencies."""
        self.state = state
        self.runtime = runtime
        self.config = runtime.config
        self.tracer = runtime.tracer
        self.session_id = runtime.session_id
        self.llm_stats = runtime.llm_stats
        self.tools = runtime.tools
        # OpenAI function-calling schemas passed to the LLM on every step.
        self.tools_schema = get_tools_schema()
        self.system_prompt = system_prompt_for(state.identity.caller_phone, runtime.config.language)

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

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

    def end_session(self, outcome: str | None = None) -> None:
        """Emit session_end once (idempotent). Call when the conversation ends."""
        from .executor_flow import register_ticket_from_state

        if self.runtime.ended.is_set():
            return
        self.runtime.ended.set()
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
            and role_of(
                (s.resolution.procedure or {}).get("verdict"),
                (s.resolution.procedure or {}).get("step"),
            )
            == "homework"
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
                    from .tooling import telemetry

                    d = telemetry(
                        self.state, self.runtime, mode="recheck", reason="hangup_net"
                    ).data
                    reason = (d.get("verdict") or {}).get("reason")
                    solved = reason is None or verdict_flag(reason, "healthy_up_to_router")
                except Exception:  # pragma: no cover - defensive
                    solved = False
            if solved:
                s.closing.case_closed = True
                s.closing.closed_reason = "resolved"
                self.tracer.emit("decision", intent="hangup_net", action="skip_solved")
            else:
                s.resolution.procedure.setdefault("escalate_reason", "caller_hung_up")
                if not s.ticket.contact_phone:
                    s.ticket.contact_phone = s.identity.caller_phone
                if not s.ticket.contact_hours:
                    s.ticket.contact_hours = phrase("ticket.default_hours")
                strat = get_strategy(s.resolution.procedure.get("verdict"))
                esc = strat.by_role("escalate") if strat else None
                register_ticket_from_state(
                    self.state, self.runtime, esc.id if esc is not None else None
                )
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
        from .executor_flow import execute_tool_calls
        from .identification_flow import (
            identification_scripted_reply,
            prefill_slots_from_text,
            preflight_phone,
        )
        from .narrator_flow import build_messages, scoped_tools_schema
        from .perception_flow import pre_turn_guards, raise_clarity
        from .speculation import apply_bg_diagnosis, consume_injected_reply
        from .ticket_flow import registration_claim_guard
        from .walker_flow import scripted_wait_ack

        # Hardcoded greeting (first turn, no input) — the node yields the fixed
        # opening line, not an LLM call. The caller's number is pre-flighted
        # while the greeting plays.
        if user_input is None and self.state.dialog.turn_count == 0:
            preflight_phone(self.state, self.runtime)
            greeting = self.config.greeting_message
            self.state.messages.append({"role": "assistant", "content": greeting})
            self.state.dialog.turn_count += 1
            self.tracer.emit("agent_reply", text=greeting)
            yield greeting
            return

        # Repeat-guard: snapshot progress BEFORE the deterministic NLU prefill, so a
        # slot/problem filled THIS turn counts as progress and clears the counter.
        self.state.turn.progress_key_at_start = progress_key(self.state)
        self.runtime.cancel.clear()  # a stale barge-in never cancels a NEW turn
        # Ticket-node turns skip the diagnosis ingest — without this, the
        # PREVIOUS turn's "supratau" directive leaks into their replies.
        if self.state.ticket.stage:
            self.state.turn.understanding = None

        self.state.dialog.last_heard = (user_input or "").strip()
        from .resolution import detect_turn_intent

        self.state.dialog.last_intent = detect_turn_intent(user_input)
        raise_clarity(self.state, user_input)
        # S2 (2026-08-24): a background telemetry read finished while the
        # caller was busy — fold it in at the deterministic turn start, but
        # ONLY as a refresh: in the solution/bridge phase, or when the fresh
        # verdict FLIPS the story, it is discarded (live: the bg read saw the
        # just-plugged PC, the narrative turned foreign_mac mid-bridge and the
        # agent asked "ar keitėte routerį?" over a working bind). The solution
        # steps (verify_device_visible / the bridge verify) do their own reads at the right
        # moments.
        apply_bg_diagnosis(self.state, self.runtime)
        if user_input:
            self.tracer.emit("user_turn", text=user_input)
            # The deterministic head may have run EARLIER (diagnose node, A-2
            # 2026-09-07) — the latch prevents a double prefill/guards run.
            if self.state.turn.pre_turn_head_done:
                self.state.turn.pre_turn_head_done = False
            else:
                prefill_slots_from_text(self.state, self.runtime, user_input)
                pre_turn_guards(self.state, self.runtime, user_input)

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
        scripted = identification_scripted_reply(
            self.state, self.runtime, self.state.dialog.last_heard
        )
        if scripted is not None:
            yield self._emit_scripted_reply(scripted)
            return

        # D5 (live 2026-08-25: 'Gerai, palauksiu' cost 2.8–12 s of LLM): a bare
        # wait signal at a standing client action is acknowledged scripted.
        wait = scripted_wait_ack(self.state, self.runtime)
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
            injected = consume_injected_reply(self.state, self.runtime)
            if injected is not None:
                yield injected
                self.state.messages.append({"role": "assistant", "content": injected})
                self._finalize_reply(injected)
                return

            # The user message is already on the history (appended up front, so
            # scripted turns record it too); the prompt builds from history.
            messages = build_messages(self.state, self.runtime, None, node_prompt, allowed_tools)

            try:
                # Manual consumption instead of `yield from`: the cancel flag is
                # checked BETWEEN TOKENS — closing the inner generator closes the
                # LLM HTTP stream, so the generation itself stops (PR3).
                inner = stream_tool_completion(
                    messages=messages,
                    tools=scoped_tools_schema(self.state, self.runtime, allowed_tools),
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
                    if self.runtime.cancel.is_set():
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
                execute_tool_calls(self.state, self.runtime, message)
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
            extra = registration_claim_guard(self.state, self.runtime, content)
            if extra:
                content += extra
                self.state.messages[-1]["content"] = content
                yield extra
            self._finalize_reply(content)
            return

        yield self.config.timeout_message

    def _stuck_backstop(self) -> tuple[str, bool] | None:
        """Deterministic escalation (text, should_close) once the prompt-level nudge
        has failed — fired BEFORE the LLM (so it works with token streaming): at 3
        offer the account code, at 4 register + close. None below that."""
        n = self.state.dialog.stuck_count
        if n >= 4:
            return (phrase("system.stuck_register"), True)
        if n >= 3:
            return (phrase("system.stuck_offer_code"), False)
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
        from .closing_flow import maybe_end_on_goodbye

        text, should_close = backstop
        if should_close:
            self.state.closing.case_closed = True
            self.state.closing.closed_reason = "declined"
        else:
            self.state.dialog.stuck_count += 1  # advance the ladder for the next turn
        self.state.messages.append({"role": "assistant", "content": text})
        if is_question(text):
            self.state.dialog.last_question = text
        maybe_end_on_goodbye(self.state, self.runtime, text)
        emit_case(self.tracer, self.state)
        self.tracer.emit("stuck", count=self.state.dialog.stuck_count, repeated=False)
        self.tracer.emit("agent_reply", text=text)
        return text

    def _finalize_reply(self, text: str) -> None:
        """Shared end-of-turn bookkeeping for a customer-facing reply: update the
        repeat-guard, emit the case snapshot + the reply trace."""
        from .closing_flow import maybe_end_on_goodbye

        self._track_stuck(text)
        maybe_end_on_goodbye(self.state, self.runtime, text)
        emit_case(self.tracer, self.state)
        self.tracer.emit("agent_reply", text=text)
