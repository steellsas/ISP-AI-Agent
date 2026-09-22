"""The effect gate — what a plan may actually DO to the call (D-04, D-16, D-17).

Every effect of a turn is an `Action` on its TurnPlan, and every Action comes through
here: an action outside the closed set, a forbidden one, or one that needs a consent the
caller has not given is dropped (its words stay). The solver's own proposals are judged
by `decide/solver_guard.py`.
"""

from __future__ import annotations

# Engine actions a plan may name besides the tool catalog and the active procedure's roles.
ENGINE_TOOLS = frozenset({"preflight_phone"})
PROCEDURE_ACTIONS = frozenset({"run_due_action", "escalate"})
# Why a call may close (Action(type="close", name=...)): the contact record's reasons
# plus the stuck ladder's own close.
CLOSE_REASONS = frozenset(
    {"resolved", "registered", "declined", "callback", "inform", "outage", "stuck", "keep"}
)


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
    if action.type == "close" and action.name not in CLOSE_REASONS:
        return f"unknown close reason {action.name!r}"
    if action.type == "procedure_step" and action.name not in PROCEDURE_ACTIONS:
        if action.name not in _active_roles(state):
            return f"no step role {action.name!r} in the active procedure"
    if action.consent == "required" and not state.dialog.consents.get(action.name or ""):
        return f"no consent for {action.name!r}"
    return None


def _tool_names() -> frozenset[str]:
    """Every tool a plan may name — the manifests (wave 2c), which are also what the
    gateway enforces; REAL_TOOLS is the demo's implementation of them."""
    from ..contract import tools as manifests

    return frozenset(manifests.names())


def _active_roles(state) -> set[str]:
    from ..resolution import get_strategy

    strat = get_strategy((state.resolution.procedure or {}).get("verdict"))
    return {s.role for s in strat.steps} if strat else set()
