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

Thresholds come from knowledge/limits.yaml (`default_policy()`).
The counters are owned by the caller and passed in, so the gate stays pure.
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


# --- The plan gate (D-04 closed action set, D-16 consent, D-17 policies) ------------------

# Engine actions a plan may name besides the tool catalog and the active procedure's roles.
ENGINE_TOOLS = frozenset({"preflight_phone"})
PROCEDURE_ACTIONS = frozenset({"run_due_action", "escalate"})


def check_plan(state, rt, plan):
    """The plan as it may run: an action outside the closed set, a forbidden one, or one
    that needs a consent the caller has not given is dropped (its words stay)."""
    reason = _rejection(state, plan.action)
    if reason is None:
        return plan
    rt.tracer.emit("gate", action=plan.action.type, name=plan.action.name, rejected=reason)
    from .plan import Action

    return plan.model_copy(update={"action": Action(type="none"), "rule": f"{plan.rule}.gated"})


def _rejection(state, action) -> str | None:
    from ..contract import policies

    if action.type == "none":
        return None
    if action.name and action.name in policies.get().forbidden_actions:
        return f"forbidden action {action.name!r}"
    if action.type == "tool" and action.name not in _tool_names() | ENGINE_TOOLS:
        return f"unknown tool {action.name!r}"
    if action.type == "procedure_step" and action.name not in PROCEDURE_ACTIONS:
        if action.name not in _active_roles(state):
            return f"no step role {action.name!r} in the active procedure"
    if action.consent == "required" and not state.dialog.consents.get(action.name or ""):
        return f"no consent for {action.name!r}"
    return None


def _tool_names() -> frozenset[str]:
    from ..tools import REAL_TOOLS

    return frozenset(t.name for t in REAL_TOOLS)


def _active_roles(state) -> set[str]:
    from ..resolution import get_strategy

    strat = get_strategy((state.resolution.procedure or {}).get("verdict"))
    return {s.role for s in strat.steps} if strat else set()
