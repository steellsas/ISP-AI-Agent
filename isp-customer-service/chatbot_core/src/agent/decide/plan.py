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
    key: str | None = None  # locale phrase key (kind=phrase); None = `text` or the action's words
    text: str | None = None  # engine-composed words (until M5 renders every phrase by key)
    goal: str | None = None  # English goal for the LLM (kind=directive)
    vars: dict[str, Any] = Field(default_factory=dict)
    # The stage whose narrator speaks a directive — and a phrase whose action had no
    # words (until M5's speak node, the stage prompts carry the goal).
    stage: str | None = None
    # A spoken question becomes the anchor the next turn is read against.
    remember_question: bool = True


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


def record(state: Any, plan: TurnPlan) -> None:
    """The turn's plan, as the trace and the checkpoint see it."""
    state.turn.plan = plan.model_dump(mode="json")


def record_stage_reply(state: Any, stage_rule: str) -> None:
    """A stage node's LLM reply that no rule planned: the procedure step it words, or
    the stage's free reply."""
    if state.turn.plan is not None:
        return
    proc = state.resolution.procedure or {}
    if proc.get("step") and state.identity.customer_id and not state.closing.case_closed:
        from ..faults import role_of

        role = role_of(proc.get("verdict"), proc.get("step")) or proc.get("step")
        record(
            state, TurnPlan(owner="procedure", rule=f"procedure.{role}", say=Say(kind="directive"))
        )
        return
    owner = stage_rule.split(".", 1)[0]
    record(state, TurnPlan(owner=owner, rule=stage_rule, say=Say(kind="directive")))
