"""
GraphState — the typed LangGraph v2 state (R1, docs/ROADMAP_REFACTORING.md §3/§6).

Design:
- Mirrors every persisted `AgentState` field 1:1 so both engines can share one
  source of truth during the strangler migration (`from_legacy` / `to_legacy`).
- Pydantic (not dataclass) so the whole state JSON-serializes losslessly — the
  readiness gate for the SqliteSaver checkpointer (time-travel, state between
  calls). `ClientProfileState`/`Slot` are already Pydantic, so nesting is free.
- One-turn scratch lives in `turn: TurnScratch`, reset via `begin_turn()` at
  every graph invocation. It is carried inside the state for node-to-node
  hand-off within a single turn, but is NOT conversation history — checkpoints
  of past turns must never be interpreted through their stale `turn` value.
  The remaining ~30 legacy `_flags` migrate here (or get promoted to real
  GraphState fields if they outlive a turn) during R3 — see roadmap §6.

Live objects (tracer, LLM clients, tool registries) never go in here — they
stay in node closures, keeping every checkpoint a plain JSON document.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from ..slots import ClientProfileState
from ..state import AgentState

# Field names shared with the legacy dataclass — derived, so a field added to
# AgentState shows up here automatically and the round-trip test catches any
# divergence in defaults or typing.
_LEGACY_FIELDS: tuple[str, ...] = tuple(f.name for f in dataclasses.fields(AgentState))


class TurnScratch(BaseModel):
    """Per-invocation scratchpad — reset by `begin_turn()`, never history."""

    user_input: str | None = None
    reply: str | None = None
    cancel_requested: bool = False
    side_topic_active: bool = False
    active_node: str | None = None


class GraphState(BaseModel):
    """The single source of truth for a call, checkpointable end-to-end."""

    # --- call / identity -------------------------------------------------
    # Default (unlike the legacy dataclass) so LangGraph can initialize the
    # state channels before the session seeds the real number on first invoke.
    caller_phone: str = "unknown"
    # dict[str, Any], not dict[str, str]: assistant tool-call messages carry a
    # `tool_calls` LIST — the narrow type poisoned the checkpoint after any LLM
    # tool round and every following turn failed validation at graph entry
    # (live 2026-08-13, stuck identification call).
    messages: list[dict[str, Any]] = Field(default_factory=list)
    profile: ClientProfileState = Field(default_factory=ClientProfileState)
    customer_id: str | None = None
    customer_name: str | None = None
    customer_address: str | None = None
    caller_name: str | None = None
    caller_relation: str | None = None
    phone_candidate: dict[str, Any] | None = None
    preflight_done: bool = False
    preflight_outage: dict[str, Any] | None = None
    address_confirmed: bool = False

    # --- problem / intake -------------------------------------------------
    problem_type: str | None = None
    problem_description: str | None = None
    anamnesis_asked: bool = False
    anamnesis_raw: str | None = None
    anamnesis_when: str | None = None
    anamnesis_trigger: str | None = None
    heard_utterances: list[str] = Field(default_factory=list)
    symptoms: dict[str, str] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)

    # --- diagnosis / hypotheses / evidence --------------------------------
    diagnosis: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hypothesis: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    failed_hypotheses: list[str] = Field(default_factory=list)
    rejected_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    pivoted_from: str | None = None
    outage_reported: bool = False

    # --- resolution walker -------------------------------------------------
    resolution: dict[str, Any] | None = None

    # --- repeat-guard / turn control ----------------------------------------
    last_question: str | None = None
    stuck_count: int = 0
    last_heard: str = ""
    clarity_level: str = "standard"
    awaiting: str | None = None
    awaiting_turns: int = 0
    step_confusions: int = 0
    last_intent: str = ""

    # --- closing / ticket ---------------------------------------------------
    case_closed: bool = False
    closed_reason: str | None = None
    contact_phone: str | None = None
    contact_hours: str | None = None
    is_complete: bool = False
    closing_turns: int = 0
    turn_count: int = 0
    max_turns: int = 20
    ticket_id: str | None = None

    # Promoted engine flag (roadmap §6), now an AgentState field too — the
    # engine's _ticket_stage property writes it, so it syncs via _LEGACY_FIELDS.
    # None | "phone" | "hours" | "done" | "cancelled"
    ticket_stage: str | None = None

    # --- per-turn scratch (not history — see module docstring) --------------
    turn: TurnScratch = Field(default_factory=TurnScratch)

    # --- turn lifecycle ------------------------------------------------------

    def begin_turn(self, user_input: str | None = None) -> None:
        """Reset the scratchpad at the start of a graph invocation."""
        self.turn = TurnScratch(user_input=user_input)

    # --- legacy bridges (removed when the strangler migration completes) -----

    @classmethod
    def from_legacy(cls, legacy: AgentState) -> GraphState:
        """Deep snapshot of the legacy dataclass (no shared mutable containers)."""
        data = {name: copy.deepcopy(getattr(legacy, name)) for name in _LEGACY_FIELDS}
        return cls.model_validate(data)

    def to_legacy(self) -> AgentState:
        """Deep snapshot back into the legacy dataclass for the old engine."""
        data = {name: copy.deepcopy(getattr(self, name)) for name in _LEGACY_FIELDS}
        return AgentState(**data)
