"""
Solver — the single DECIDER (Phase 3.8 step 2).

The walker executes a fixed step list; the solver instead REASONS: given the live
hypothesis + the caller's latest observation + the raw telemetry, it decides what to
believe and what to do next, and can revise the belief from dialogue (catching a
telemetry↔client contradiction the walker cannot). Full contract:
docs/MASTANTIS_AGENTAS_SPEC.md §③.

Principles baked in:
- Cognitive divergence, action convergence: `current_hypothesis` is FREE text (may
  exceed the verdict-tree vocabulary — e.g. "looking at the ONT, not the router"), but
  `next_action` is a STRICT enum the gate can validate.
- Single decider: the solver only PROPOSES; the engine/gate validates + executes safety
  actions. This module never touches state or runs a tool.
- Fact authority: telemetry wins for line/session facts (LOS, port, sessions — the
  caller cannot see them); the caller wins for physical-room facts telemetry cannot see
  (which box they look at, whether they seated a cable).

Slice-1 wiring is SHADOW-ONLY (react_agent._shadow_solve): it computes + logs a decision
next to the walker's move so we can compare on real calls before it ever drives a reply.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .contract import limits

logger = logging.getLogger(__name__)

# The bounded action space. The gate validates `next_action` against this; anything
# else (or an unknown hypothesis reaching a safety action) is rejected. Safety actions
# (propose_fix / escalate / close) are EXECUTED by code, never by the solver.
ALLOWED_ACTIONS = (
    "ask",  # ask the caller a question
    "disambiguate",  # make sure we mean the same thing / device (redirect)
    "instruct",  # give ONE concrete instruction
    "wait",  # caller is still doing it — hold, do not read telemetry yet
    "reread_telemetry",  # re-read the line before deciding
    "verify",  # check whether it works now
    "propose_fix",  # bind / reset — EXECUTED BY CODE
    "pivot",  # change the hypothesis
    "escalate",  # register the fault — EXECUTED BY CODE
    "close",  # resolved — EXECUTED BY CODE
)


class SolverDecision(BaseModel):
    """The solver's structured output — validated at the tool-call boundary so the model
    retries on mismatch (never free text to the client)."""

    current_hypothesis: str = Field(description="free-text belief about the cause")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    conflict_detected: bool = Field(
        default=False, description="telemetry contradicts what the caller says"
    )
    conflict_note: str | None = Field(default=None, description="what contradicts what")
    hypothesis_changed: bool = Field(default=False)
    reason_for_change: str | None = Field(
        default=None, description="internal, telemetry-grounded — for logs/evidence"
    )
    next_action: str = Field(description=f"one of: {', '.join(ALLOWED_ACTIONS)}")
    narrator_instruction: str = Field(
        description="the exact words to SAY to the caller now — natural spoken language of the call, "
        "empathetic, plain, ONE thing at a time (spoken verbatim when the solver drives)"
    )


def _system() -> str:
    from .prompts import load_node_prompt

    return load_node_prompt("sensors/solver").replace("<<actions>>", ", ".join(ALLOWED_ACTIONS))


def solve(context: str, model: str | None = None) -> SolverDecision | None:
    """Reason over the situation `context` and return a decision. None on ANY failure
    (the shadow caller just logs the miss; a live caller would fall back to the walker)."""
    if not context or not context.strip():
        return None
    try:
        from src.services.llm.client import llm_json_completion

        data = llm_json_completion(
            messages=[
                {"role": "system", "content": _system()},
                {"role": "user", "content": context},
            ],
            model=model,
            temperature=0.0,
            max_tokens=limits.get("solver_max_tokens"),
            validate_schema=SolverDecision,
        )
        decision = SolverDecision(**data)
        if decision.next_action not in ALLOWED_ACTIONS:
            logger.warning(f"solver returned unknown next_action={decision.next_action!r}")
            return None
        return decision
    except Exception as e:
        logger.warning(f"solver.solve failed: {e}")
        return None
