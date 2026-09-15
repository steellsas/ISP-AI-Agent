"""TurnPlan — the one decision a turn makes: who owns it, which rule fired, what runs
and what is said (M4, D-02).

`decide` produces exactly one plan per turn; `execute` runs its action and `narrate`
renders its `say`. Until the policy chain lands, the shadow recorder
(`decide/shadow.py`) records the plan the old code paths effectively executed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Owner = Literal[
    "intake",
    "identification",
    "inform",
    "side_topic",
    "diagnosis",
    "procedure",
    "ticket",
    "closing",
]


class Say(BaseModel):
    kind: Literal["phrase", "directive", "none"]
    key: str | None = None  # locale phrase key (kind=phrase)
    goal: str | None = None  # English goal for the LLM (kind=directive)
    vars: dict[str, Any] = Field(default_factory=dict)


class Action(BaseModel):
    type: Literal["tool", "procedure_step", "register_ticket", "append_ticket", "close", "none"]
    name: str | None = None  # tool name / step role / close reason
    args: dict[str, Any] = Field(default_factory=dict)
    consent: Literal["required", "not_required"] = "not_required"


class Contradiction(BaseModel):
    source: Literal["telemetry", "client", "analyst"]
    fact_key: str
    before_value: str | None = None
    before_quote: str | None = None  # what the client said earlier (for the confirm question)
    now_value: str | None = None


class HypothesisView(BaseModel):
    cause: str  # verdict / pack id
    status: Literal["active", "doubt", "confirming", "changed"]
    contradiction: Contradiction | None = None


class TurnPlan(BaseModel):
    owner: Owner
    rule: str  # id of the policy rule that fired, e.g. "ticket.capture_phone"
    action: Action = Field(default_factory=lambda: Action(type="none"))
    say: Say
    hypothesis: HypothesisView | None = None
    awaiting: str | None = None  # evidence key / step role / question key we wait for
    redecide_after_action: bool = False
