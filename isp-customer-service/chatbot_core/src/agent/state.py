"""
Agent State Management.

Contains the state dataclass that tracks conversation progress.
"""

from dataclasses import dataclass, field
from typing import Any

from .slots import ClientProfileState


@dataclass
class AgentState:
    """
    Agent conversation state.

    Tracks all information gathered during a customer support call.
    """

    # Call identification
    caller_phone: str

    # Conversation history (for LLM context)
    messages: list[dict[str, str]] = field(default_factory=list)

    # Structured address slots (Phase 3.5) — durable, typed identification memory
    # populated from resolve_address. Additive: the existing customer_* /
    # address_confirmed fields below still drive current behaviour; the slots are
    # the foundation the policy/NLU steps build on.
    profile: ClientProfileState = field(default_factory=ClientProfileState)

    # Customer information (populated after find_customer)
    customer_id: str | None = None
    customer_name: str | None = None  # Name from CRM (may differ from caller)
    customer_address: str | None = None

    # Pre-flight phone lookup result (the caller's number, resolved at the start
    # of the call). UNCONFIRMED — a candidate the agent offers for the caller to
    # confirm, NOT a confirmed identity. {customer_id, name, address} or None.
    phone_candidate: dict[str, Any] | None = None
    # Whether the pre-flight phone lookup has run (so "no candidate" can be told
    # apart from "lookup not done yet" — the agent only states "no account on
    # file" once we have actually checked).
    preflight_done: bool = False

    # Caller information (populated after customer confirms)
    caller_name: str | None = None  # Actual caller's name
    address_confirmed: bool = False

    # Tool observations
    observations: list[str] = field(default_factory=list)

    # Problem tracking
    problem_type: str | None = None  # internet, tv, phone, billing
    problem_description: str | None = None

    # Diagnostic findings (case state), namespaced BY DOMAIN so new fault families
    # (iptv, voip…) attach additively without touching the base flow:
    #   {"network": {group, side, action, reason, signals}}
    # Kept so the agent reconciles findings with what the customer says and never
    # loses / re-runs them. The container is extensible; we only populate domains
    # that actually exist (today: "network").
    diagnosis: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Symptoms the customer reported (case state) — deterministically extracted
    # categoricals: {lights, connection, devices, frequency, services}. Revisable;
    # feeds the agent's questioning + the eventual diagnosis. Free-form symptoms
    # (exact "when did it start") are left to the LLM / a future SLM (§12.7).
    symptoms: dict[str, str] = field(default_factory=dict)

    # Case closing (END state, Phase 3.5). case_closed flips the router to the
    # tools-less `closing` node — set ONLY by the close_case tool (model-driven, so
    # the model owns the "is the caller actually done?" judgement; never auto-set,
    # see the outage discussion). closed_reason tailors the goodbye.
    case_closed: bool = False
    closed_reason: str | None = None  # "resolved" | "outage" | "declined"
    # An active outage was reported for the caller's street. This does NOT close the
    # case (the caller still asks "when fixed? / compensation?") — it switches the
    # agent into a restricted mode: answer outage follow-ups, no more diagnosis.
    outage_reported: bool = False

    # Conversation control
    is_complete: bool = False
    turn_count: int = 0
    max_turns: int = 20

    # Ticket info (if created)
    ticket_id: str | None = None

    def add_observation(self, observation: str):
        """Add tool observation to history."""
        self.observations.append(observation)

    def set_customer_info(self, customer_id: str, name: str = None, address: str = None):
        """Set customer information from CRM lookup."""
        self.customer_id = customer_id
        self.customer_name = name
        self.customer_address = address

    def confirm_address(self, caller_name: str = None):
        """Mark address as confirmed by caller."""
        self.address_confirmed = True
        if caller_name:
            self.caller_name = caller_name

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "caller_phone": self.caller_phone,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "caller_name": self.caller_name,
            "address_confirmed": self.address_confirmed,
            "problem_type": self.problem_type,
            "problem_description": self.problem_description,
            "is_complete": self.is_complete,
            "turn_count": self.turn_count,
            "ticket_id": self.ticket_id,
        }
