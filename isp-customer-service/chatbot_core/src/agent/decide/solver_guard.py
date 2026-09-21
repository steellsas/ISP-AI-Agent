"""Solver guard — validate + safeguard the LLM solver's proposal (D-04).

This is NOT the effect gate: it judges a DECISION the solver suggests (is the action in
the closed set, is the belief mapped, has the solver been spinning or unsure), and it
never looks at state or runs anything. The effect gate — what a plan may actually DO to
the call — is `decide/gate.py::check_plan` (wave 1b split the two: one gate for effects,
one guard for the solver's reasoning).

Responsibilities:
1. Schema/enum validation — `next_action` must be a known action, else fall back to `ask`.
2. Cognitive divergence, ACTION convergence — a safety MUTATION (`propose_fix`) on a
   belief that maps to no known verdict cause is REJECTED (downgraded to `verify`).
3. Internal-loop cap — the "silent" actions can chain only so many times before a
   client-facing action is forced.
4. Bailout — a low-confidence streak or too many cycles on one step forces `escalate`.

Thresholds come from knowledge/limits.yaml; the counters are owned by the caller and
passed in, so this stays a pure function.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import limits
from .solver import ALLOWED_ACTIONS, SolverDecision

# Actions executed by CODE, never by the solver. propose_fix is a MUTATION (bind/reset);
# escalate/close are terminal. Only the mutation requires a hypothesis mapped to a known
# cause — escalate/close are safe regardless of how the belief is worded.
SAFETY_ACTIONS = frozenset({"propose_fix", "escalate", "close"})
MUTATION_ACTIONS = frozenset({"propose_fix"})
# "Silent" internal actions that do not face the caller — capped so we cannot spin.
INTERNAL_ACTIONS = frozenset({"reread_telemetry", "pivot"})


def default_policy() -> dict:
    """The gate thresholds (knowledge/limits.yaml `solver_*`)."""
    return {
        "confidence_floor": limits.get("solver_confidence_floor"),
        "low_conf_max": limits.get("solver_low_conf_max"),
        "cycles_max": limits.get("solver_cycles_max"),
        "internal_hops_max": limits.get("solver_internal_hops_max"),
    }


@dataclass
class GateResult:
    """What the engine should ACTUALLY do after gating the solver's proposal."""

    action: str  # the (possibly overridden) action to execute
    accepted: bool  # True if the solver's action passed unchanged
    bailout: bool = False  # True if the safeguard forced escalation
    reason: str | None = None  # why it was overridden (for the trace / debugging)


def gate(
    decision: SolverDecision | None,
    *,
    known_hypotheses: set[str] | frozenset[str],
    low_conf_streak: int = 0,
    cycles_in_step: int = 0,
    internal_hops: int = 0,
    policy: dict | None = None,
) -> GateResult:
    """Validate + safeguard a solver decision. Pure: same inputs -> same result.

    Order matters — the bailout safeguard wins over everything (a stuck/uncertain agent
    escalates rather than acting), then structural validity, then the safety-mapping rule.
    """
    p = {**default_policy(), **(policy or {})}

    # No decision at all (solver failed) -> ask, so the turn never stalls.
    if decision is None:
        return GateResult(action="ask", accepted=False, reason="no solver decision")

    # 1) Bailout FIRST — a stuck or persistently unsure agent must stop grinding.
    if low_conf_streak >= p["low_conf_max"]:
        return GateResult(
            action="escalate",
            accepted=False,
            bailout=True,
            reason=f"low confidence {low_conf_streak}x in a row",
        )
    if cycles_in_step > p["cycles_max"]:
        return GateResult(
            action="escalate",
            accepted=False,
            bailout=True,
            reason=f"stuck on the same step {cycles_in_step}x",
        )

    # 2) Structural validity — unknown action falls back to asking the caller.
    if decision.next_action not in ALLOWED_ACTIONS:
        return GateResult(
            action="ask",
            accepted=False,
            reason=f"unknown action {decision.next_action!r}",
        )

    # 3) Internal-loop cap — do not spin on silent actions; force a client-facing turn.
    if decision.next_action in INTERNAL_ACTIONS and internal_hops >= p["internal_hops_max"]:
        return GateResult(
            action="ask",
            accepted=False,
            reason=f"internal-hop cap ({internal_hops})",
        )

    # 4) Action convergence — a MUTATION on an unmapped free-text belief is rejected;
    #    reason freely, but only bind/reset when the belief maps to a known cause.
    if decision.next_action in MUTATION_ACTIONS and decision.current_hypothesis not in (
        known_hypotheses or set()
    ):
        return GateResult(
            action="verify",
            accepted=False,
            reason=f"mutation on unmapped hypothesis {decision.current_hypothesis!r}",
        )

    # Accepted as proposed.
    return GateResult(action=decision.next_action, accepted=True)
