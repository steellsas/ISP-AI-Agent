"""
GraphState — the single source of truth for a call (D-01).

Design:
- Pydantic so the whole state JSON-serializes losslessly — every checkpoint is
  a plain document (SqliteSaver: time-travel, state between turns).
- Grouped by concern: identity · intake · diagnosis · resolution · ticket ·
  dialog · closing, plus `messages` (the LLM transcript) and `turn`.
- One-turn scratch lives in `turn: TurnScratch`, replaced at every graph
  invocation. It is carried inside the state for node-to-node hand-off within a
  single turn, but is NOT conversation history — checkpoints of past turns must
  never be interpreted through their stale `turn` value.

Live objects (tracer, LLM clients, tool registries) never go in here — they
stay in node closures / the runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..config import AgentConfig
from ..slots import ClientProfileState


class IdentityState(BaseModel):
    """Who is calling and which account the call is about."""

    # Default so LangGraph can initialize the channels before the session seeds
    # the real number on the first invoke.
    caller_phone: str = "unknown"
    # Structured address slots — durable, typed identification memory.
    profile: ClientProfileState = Field(default_factory=ClientProfileState)
    customer_id: str | None = None
    customer_name: str | None = None  # the ACCOUNT holder's name from the CRM
    customer_address: str | None = None
    # Who is actually ON THE PHONE — call record only, NEVER compared to the
    # account name (holder, family, tenant or helper may call).
    caller_name: str | None = None
    # "holder" | "family" | "tenant" | "helper" | "unknown" — a record, never a gate.
    caller_relation: str | None = None
    # Pre-flight phone lookup: an UNCONFIRMED candidate {customer_id, name, address}.
    phone_candidate: dict[str, Any] | None = None
    preflight_done: bool = False
    # Active outage on the caller's number's street: {street, eta, description}.
    preflight_outage: dict[str, Any] | None = None
    address_confirmed: bool = False

    def set_customer(self, customer_id: str, name: str | None = None, address: str | None = None):
        """Commit the identified account (CRM lookup result)."""
        self.customer_id = customer_id
        self.customer_name = name
        self.customer_address = address


class IntakeState(BaseModel):
    """What the caller reported: the problem, its history and symptoms."""

    problem_type: str | None = None  # internet_down, tv, …
    # The PRIMARY goal never flips mid-call; later mentions of OTHER problems
    # land here — asked about at the end, listed on the ticket.
    secondary_problems: list[dict[str, Any]] = Field(default_factory=list)
    problem_description: str | None = None
    # The ONE history question ("kada pastebėjote, po ko dingo?"), asked once.
    anamnesis_asked: bool = False
    anamnesis_raw: str | None = None
    anamnesis_when: str | None = None
    anamnesis_trigger: str | None = None
    # Categorical symptoms: {lights, connection, devices, frequency, services}.
    symptoms: dict[str, str] = Field(default_factory=dict)
    # Everything the caller said, verbatim — lets the LLM reconcile an address
    # split by VAD/STT into garbled fragments.
    heard_utterances: list[str] = Field(default_factory=list)
    # Raw tool observations.
    observations: list[str] = Field(default_factory=list)


class DiagnosisState(BaseModel):
    """What we believe is wrong and the evidence behind it."""

    # Verdicts namespaced BY DOMAIN: {"network": {group, side, action, reason, signals}}.
    verdicts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # {"cause", "because": [..], "status": testing|confirmed|rejected, "settled_by"}
    hypothesis: dict[str, Any] | None = None
    # Evidence ledger: {key: {value, source, turn, history, conflict}} (agent/evidence.py).
    evidence: dict[str, Any] = Field(default_factory=dict)
    # Causes telemetry already disproved — never re-tried.
    failed_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    # The just-rejected cause, carried for ONE reply so the rethink is said aloud.
    pivoted_from: str | None = None
    # An active outage was reported for the caller's street (does NOT close the case).
    outage_reported: bool = False


class ResolutionState(BaseModel):
    """The active strategy/procedure position."""

    # {"verdict", "step", "asked", …} once a verdict maps to a strategy; the
    # engine walks its steps deterministically. None = generic inform/instruct.
    procedure: dict[str, Any] | None = None


class TicketState(BaseModel):
    """The contact dialogue before registration and the registered ticket."""

    ticket_id: str | None = None
    # None | "phone" | "hours" | "done" | "cancelled"
    stage: str | None = None
    contact_phone: str | None = None
    contact_hours: str | None = None


class DialogState(BaseModel):
    """Turn control: repeat-guard, what we wait for, how the caller follows."""

    last_question: str | None = None
    # Consecutive question-turns with NO progress (drives nudge -> backstop).
    stuck_count: int = 0
    # What the caller said THIS turn ("" = silence / nothing usable).
    last_heard: str = ""
    # "standard" | "basic" — raised for the rest of the call once the caller is lost.
    clarity_level: str = "standard"
    # None | "client_answer" | "client_action" | "system_check"
    awaiting: str | None = None
    awaiting_turns: int = 0
    # How many times the caller said they do not follow THIS step.
    step_confusions: int = 0
    # resolution.detect_turn_intent of the last turn — only "answer"/"done" advance a step.
    last_intent: str = ""
    turn_count: int = 0
    max_turns: int = AgentConfig.max_turns


class ClosingState(BaseModel):
    """The END stage."""

    case_closed: bool = False
    closed_reason: str | None = None  # "resolved" | "outage" | "declined" | …
    is_complete: bool = False  # the transport hangs up once True
    closing_turns: int = 0


class TurnScratch(BaseModel):
    """Per-invocation scratchpad — replaced every turn, never history."""

    user_input: str | None = None
    reply: str | None = None
    cancel_requested: bool = False
    side_topic_active: bool = False
    active_node: str | None = None


# The persisted groups, in declaration order (everything but the turn scratch).
STATE_GROUPS: tuple[str, ...] = (
    "messages",
    "identity",
    "intake",
    "diagnosis",
    "resolution",
    "ticket",
    "dialog",
    "closing",
)


class GraphState(BaseModel):
    """The single source of truth for a call, checkpointable end-to-end."""

    # dict[str, Any], not dict[str, str]: assistant tool-call messages carry a
    # `tool_calls` LIST (live 2026-08-13: the narrow type poisoned the checkpoint).
    messages: list[dict[str, Any]] = Field(default_factory=list)
    identity: IdentityState = Field(default_factory=IdentityState)
    intake: IntakeState = Field(default_factory=IntakeState)
    diagnosis: DiagnosisState = Field(default_factory=DiagnosisState)
    resolution: ResolutionState = Field(default_factory=ResolutionState)
    ticket: TicketState = Field(default_factory=TicketState)
    dialog: DialogState = Field(default_factory=DialogState)
    closing: ClosingState = Field(default_factory=ClosingState)
    turn: TurnScratch = Field(default_factory=TurnScratch)
