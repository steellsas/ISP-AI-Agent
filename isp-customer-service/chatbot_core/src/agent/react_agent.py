"""
The narrator — one speaking turn of the call.

`begin_turn` does the turn bookkeeping (barge-in flag, heard text, history) and
`llm_reply` streams the words: the speaker sees the context card and the owner's prompt,
has NO tools, and says what the plan chose (D-02). M5 moves what is left of this class
into agent/speak/.

Callers use agent.session.AgentSession; the engine is internal.
"""

import logging

# LLM client
from .contract.locale import phrase
from .faults import role_of, verdict_flag
from .graph_v2.state import GraphState
from .runtime import AgentRuntime
from .trace import tools_called_this_session, trace_note

logger = logging.getLogger(__name__)


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

    def get_stats(self) -> dict:
        """Get accumulated LLM statistics."""
        return self.llm_stats.to_dict()

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
