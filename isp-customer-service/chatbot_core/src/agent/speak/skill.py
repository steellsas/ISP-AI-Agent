"""Which SKILL this reply needs (wave 2b).

The narrator used to get one big prompt per plan owner — the whole persona, every stage
rule and every example, ~3500 tokens for a reply of ~90. A turn does ONE thing, so it is
handed one skill: what that thing is, three examples of how it sounds, and nothing else.

The skill follows from the plan decide already made (its rule and the directives it left
on the turn) — no new decision here, just a lookup.
"""

from __future__ import annotations

from typing import Any

# Every skill has prompts/skills/<name>.md and locale examples skill_<name>.md.
SKILLS = (
    "ask_identity",
    "ask_fact",
    "instruct_step",
    "explain_finding",
    "reexplain_confused",
    "answer_side",
    "ticket_offscript",
    "inform_news",
    "goodbye",
)

# A plan rule's family -> the skill, when the turn's own directives do not say otherwise.
_BY_FAMILY = {
    "identification": "ask_identity",
    "intake": "ask_identity",
    "side_topic": "answer_side",
    "ticket": "ticket_offscript",
    "inform": "inform_news",
    "closing": "goodbye",
}


def skill_for(state: Any, owner: str) -> str:
    """The skill this reply needs."""
    plan = state.turn.plan or {}
    rule = str(plan.get("rule") or "")
    directives = state.turn.directives
    understanding = state.turn.understanding or {}

    # The caller said they do not follow — that owns the reply whatever the stage.
    if understanding.get("type") == "confusion" and understanding.get("confusion"):
        return "reexplain_confused"
    # A finding / recap moment is announced, not asked.
    if directives.findings or directives.recap:
        return "explain_finding"
    # Wave 3: on the fault path the CASE's module says what this turn is — a question, an
    # instruction, or the engine announcing what it is doing. Before this the old evidence
    # directive chose `ask_fact` and the narrator asked a question while the card held a
    # bind announcement (full eval, S1).
    module_skill = _case_skill(state, rule)
    if module_skill:
        return module_skill
    if directives.evidence:
        return "ask_fact"
    family = rule.split(".", 1)[0] if rule else owner
    if family in _BY_FAMILY:
        return _BY_FAMILY[family]
    # The fault path: a step to carry out, else the next fact to learn.
    if (state.resolution.procedure or {}).get("step") and _step_instructs(state):
        return "instruct_step"
    return "ask_fact"


# What the Case's module kinds sound like.
_BY_KIND = {
    "ask": "ask_fact",
    "instruct": "instruct_step",
    "action": "inform_news",  # the engine acts; the caller is told what is happening
    "verify": "ask_fact",
    "escalate": "ticket_offscript",
}


def _case_skill(state: Any, rule: str) -> str | None:
    """The skill for a Case-planned turn, from the module it is running."""
    if not rule.startswith("case."):
        return None
    module = rule.split(".", 1)[1].removeprefix("learn.")
    if module in ("probe", "reflect"):
        return None  # nothing is said for a check we run ourselves
    if module == "ask":
        return "ask_fact"
    if module == "resolved":
        return "explain_finding"
    if module == "escalate":
        return "ticket_offscript"
    from ..contract import cards as catalog

    spec = catalog.module(module)
    return _BY_KIND.get(spec.kind) if spec else None


def _step_instructs(state: Any) -> bool:
    """Does the active step ask the caller to DO something (vs. to tell something)?"""
    from ..resolution import StepKind, get_strategy

    procedure = state.resolution.procedure or {}
    strategy = get_strategy(procedure.get("verdict"))
    step = strategy.step(procedure.get("step", "")) if strategy else None
    return step is not None and step.kind in (StepKind.INSTRUCT, StepKind.ACTION)
