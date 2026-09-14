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
from ..evidence import EvidenceConflict, FactConfirm
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

    # --- identification ladder -------------------------------------------------
    # Account-code rung: the caller is asked for the abonento kodas; grace turns
    # let a partly dictated code finish before the ladder moves on.
    account_code_mode: bool = False
    account_code_grace_turns: int = 0
    # Address rung counters / one-shot warnings.
    address_empty_turns: int = 0
    address_unrecognized_turns: int = 0
    address_warned: bool = False
    address_encouraged: bool = False
    address_resolve_failures: int = 0
    # A city the lookup found the street in, offered back to the caller.
    suggested_city: str | None = None
    # Failed street readings across turns — the SAME transcript repeating means
    # "heard right, street absent" (honest not-exists).
    street_attempts: list[str] = Field(default_factory=list)
    street_not_exists_due: bool = False
    street_not_exists_said: bool = False
    city_not_served_said: bool = False
    # Spelling rung — armed after the spell ask went out.
    spell_mode: bool = False
    # The caller was identified this turn (one-shot, read by the narration).
    just_identified: bool = False
    # Identified mid-turn: the diagnosis result is deferred behind the caller intro.
    result_pending: bool = False
    # Re-identification confirm ("ne mano adresas"): the utterance, ask state, re-ask.
    reopen_confirm_utterance: str | None = None
    reopen_confirm_asked: bool = False
    reopen_confirm_asks: int = 1
    reopen_reask_due: bool = False
    # Holder-name clarification (privacy: the DB name is never spoken).
    holder_clarify_open: bool = False
    holder_clarify_asked: bool = False
    # The caller just introduced themselves — accept warmly, once.
    caller_name_heard: bool = False

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
    # Out-of-scope problem named by the caller (competence boundary), one-shot.
    boundary_problem: str | None = None
    # Tentative problem label awaiting the caller's confirmation.
    problem_guess: str | None = None
    ask_problem_count: int = 0
    # The opening utterance was heard before the problem was clear — one-shot note.
    opening_heard_note: bool = False


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

    # --- evidence dialogue ------------------------------------------------------
    # The diagnosis result was told to the caller (never repeated).
    news_delivered: bool = False
    # How many times each evidence key was asked.
    evidence_ask_counts: dict[str, int] = Field(default_factory=dict)
    # The evidence key whose question is out (a bare "taip/ne" maps to it).
    pending_evidence_key: str | None = None
    # A client fact contradicted an earlier value: the clarify is due / out.
    evidence_conflict: EvidenceConflict | None = None
    evidence_conflict_asked_key: str | None = None
    # A story-flipping volunteered fact parked for one confirm question / asked.
    fact_confirm_pending: FactConfirm | None = None
    fact_confirm_asked: FactConfirm | None = None
    # The just-landed answer's declared meaning [label, value, meaning], one-shot.
    fact_meaning: list[str] | None = None
    # Keys whose give-up marker got its one revival ask.
    revived_evidence_keys: list[str] = Field(default_factory=list)
    # Facts recap / refute-confirm sub-dialogue progress ("" = not started).
    facts_recap_state: str = ""
    refute_confirm_state: str = ""
    findings_announced: bool = False
    # A finding to prepend to the next reply.
    pending_announcement: str = ""


class ResolutionState(BaseModel):
    """The active strategy/procedure position."""

    # {"verdict", "step", "asked", …} once a verdict maps to a strategy; the
    # engine walks its steps deterministically. None = generic inform/instruct.
    procedure: dict[str, Any] | None = None

    # --- solver ---------------------------------------------------------------
    solver_prev_step: str | None = None
    solver_cycles: int = 0
    # Consecutive low-confidence solver decisions.
    solver_low_conf_streak: int = 0
    solver_internal_hops: int = 0
    # --- solver drive (the solver owns the whole turn) ---------------------------
    drive_turns: int = 0
    drive_repeats: int = 0
    drive_last_reply: str | None = None
    drive_last_action: str | None = None
    drive_disabled: bool = False
    # --- dead-router bridge (internet cable straight into the PC) ---------------
    bridge_offered: bool = False
    bridge_plug_reported: bool = False
    bridge_bound: bool = False
    bridge_fail_stage: int = 0
    # --- escalation --------------------------------------------------------------
    escalate_clarify_asked: bool = False
    escalate_clarify_due: bool = False


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
    # Consecutive side-topic (deviation) turns.
    side_topic_streak: int = 0
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


class TurnDirectives(BaseModel):
    """Narrator directives composed this turn, consumed by the facts block."""

    evidence: dict[str, Any] | None = None
    findings: dict[str, Any] | None = None
    recap: dict[str, Any] | None = None
    ident: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None


class TurnScratch(BaseModel):
    """Per-invocation scratchpad — replaced every turn, never history."""

    user_input: str | None = None
    reply: str | None = None
    cancel_requested: bool = False
    side_topic_active: bool = False
    active_node: str | None = None
    # Identification notes for this turn's facts block.
    address_lookup_note: str | None = None
    address_confirm_note: str | None = None
    db_address_note: str | None = None
    reopen_note: bool = False
    # Perception of this turn: the understand pass and the step classifier.
    understanding: dict[str, Any] | None = None
    perception_step: dict[str, Any] | None = None
    # The evidence key the caller reported as done this turn.
    done_report_key: str | None = None
    directives: TurnDirectives = Field(default_factory=TurnDirectives)


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
