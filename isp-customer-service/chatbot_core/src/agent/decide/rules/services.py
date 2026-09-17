"""Service rules (D-10, D-12) — what the customer's service profile decides.

A complaint about a service the contract does not have is answered, not diagnosed. A
complaint about a service that depends on another (IPTV over the internet) is checked on
the service it depends on first: when that one is broken, it is fixed and the dependent
service is re-checked at the end; when it is healthy, the complaint is a fault of its own.
"""

from __future__ import annotations

from typing import Any


def route(state: Any) -> str | None:
    """How the reported problem meets the profile: `not_subscribed`, `depends` (the
    service rides on another one), `own`, or None when there is nothing to decide (no
    profile yet, or a complaint not about a service)."""
    from ...intents import intent_service
    from ...services import depends_on, subscribed

    service = intent_service(state.intake.problem_type)
    profile = state.identity.service_profile
    if not service or profile is None:
        return None
    plan = subscribed(profile, service)
    if plan is None:
        return "not_subscribed"
    return "depends" if depends_on(service, plan.get("technology")) else "own"


def not_subscribed(state: Any, rt: Any) -> None:
    """Say it plainly: the contract has no such service — nothing to check, no ticket."""
    state.diagnosis.verdicts["network"] = {"reason": "service_not_subscribed", "skipped": True}
    rt.tracer.emit("verdict", reason="service_not_subscribed", source="service_profile")
    rt.tracer.emit(
        "decision", intent="service", action="not_subscribed", value=state.intake.problem_type
    )


def depends_on_broken(state: Any) -> bool:
    """The service the complaint depends on is itself broken (the telemetry verdict is not
    "healthy up to the router") — fixing it is the first move."""
    from ...faults import verdict_flag

    reason = (state.diagnosis.verdicts.get("network") or {}).get("reason")
    return bool(reason) and not verdict_flag(reason, "healthy_up_to_router")


def recheck_after_fix(state: Any, rt: Any) -> None:
    """The dependent service goes on the closing's list: once the fix is done, the
    caller is asked whether it works now (D-12)."""
    from ...intents import intent_service

    service = intent_service(state.intake.problem_type)
    if any(x.get("source") == "dependency" for x in state.intake.secondary_problems):
        return
    state.intake.secondary_problems.append(
        {
            "type": state.intake.problem_type,
            "service": service,
            "text": service,
            "source": "dependency",
        }
    )
    rt.tracer.emit("decision", intent="service", action="recheck_after_fix", value=service)
