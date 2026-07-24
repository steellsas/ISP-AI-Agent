"""
Gate — validate + safeguard the solver's decision (Phase 3.8 step 3).

The solver REASONS freely; the gate is the deterministic boundary that decides what is
allowed to actually happen (docs/MASTANTIS_AGENTAS_SPEC.md §④). It is pure 🔒 mechanism
— no LLM, no I/O, no state — so it is fully unit-testable and cannot be talked out of a
safety rule by a clever hypothesis.

Responsibilities:
1. Schema/enum validation — `next_action` must be a known action, else fall back to `ask`.
2. Cognitive divergence, ACTION convergence — the hypothesis may be free text, but a
   safety MUTATION (`propose_fix`) on a hypothesis that maps to no known verdict cause is
   REJECTED (downgraded to `verify`): reason freely, act only on mapped beliefs.
3. Internal-loop cap — the "silent" actions (`reread_telemetry`, `pivot`) can chain only
   so many times before a client-facing action is forced (no infinite internal spinning).
4. Bailout — a low-confidence streak or too many cycles on the same step forces
   `escalate` (register the fault) so the agent never grinds the caller forever.

Thresholds live in DEFAULT_POLICY here for now; they move to policy.yaml (⚙️) later.
The counters are owned by the caller and passed in, so the gate stays pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .solver import ALLOWED_ACTIONS, SolverDecision

# Actions executed by CODE, never by the solver. propose_fix is a MUTATION (bind/reset);
# escalate/close are terminal. Only the mutation requires a hypothesis mapped to a known
# cause — escalate/close are safe regardless of how the belief is worded.
SAFETY_ACTIONS = frozenset({"propose_fix", "escalate", "close"})
MUTATION_ACTIONS = frozenset({"propose_fix"})
# "Silent" internal actions that do not face the caller — capped so we cannot spin.
INTERNAL_ACTIONS = frozenset({"reread_telemetry", "pivot"})

DEFAULT_POLICY = {
    "confidence_floor": 0.4,  # below this counts toward the low-confidence streak
    "low_conf_max": 3,  # this many low-confidence turns in a row -> bail out
    "cycles_max": 3,  # more than this many turns on the SAME step -> bail out
    "internal_hops_max": 2,  # consecutive silent actions before a client action is forced
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
    p = {**DEFAULT_POLICY, **(policy or {})}

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
