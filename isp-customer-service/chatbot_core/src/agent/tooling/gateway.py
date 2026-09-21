"""
ToolGateway — the ONE place a tool call happens.

run(): trace `tool_call` (with the caller's reason) → deterministic access gate
→ provider call → state update from the observation → trace `tool_result`.
Callers get a ToolResult; the observation stays the tool's JSON string.

What the gate allows comes from the tool's MANIFEST (knowledge/tools/*.yaml, wave 2c):
`requires` says who may call it, `guards` how often and when. The rules used to live in
code and in policies.yaml; now a new tool needs no gateway edit, and every refusal names
the guard it came from.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.ports.tools import ToolProvider

from ..contract import tools as manifests
from ..trace import trace_tool_result

# Technical tools that must NOT run before the customer is identified
# (Phase 3.5 §5 tool-access gate). Read-only lookups stay open pre-id.


@dataclass(frozen=True)
class ToolResult:
    name: str
    args: dict[str, Any]
    # The tool's JSON string (or the gate's corrective refusal).
    observation: str
    ms: int = 0
    gated: bool = False
    data: dict[str, Any] = field(default_factory=dict)


def _parse(observation: str) -> dict[str, Any]:
    try:
        data = json.loads(observation)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


class ToolGateway:
    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def run(
        self,
        state: Any,
        rt: Any,
        name: str,
        args: dict[str, Any],
        *,
        reason: str,
        apply: bool = True,
    ) -> ToolResult:
        """Run one tool call for the call in `state`. `apply=False` leaves the
        state untouched (read-only rechecks)."""
        spec = manifests.manifest(name)
        rt.tracer.emit(
            "tool_call",
            name=name,
            args=args,
            reason=reason,
            capability=spec.capability if spec else None,
            adapter=spec.adapter if spec else None,
        )
        refusal = gate(state, rt, name, args)
        if refusal is not None:
            observation, ms, gated = refusal, 0, True
        else:
            started = time.perf_counter()
            observation = self.provider.execute(name, args)
            ms, gated = round((time.perf_counter() - started) * 1000.0), False
            _record_call(state, name)
        if apply:
            from ..execute.observe import update_state_from_observation

            update_state_from_observation(state, rt, name, observation)
        trace_tool_result(rt.tracer, name, observation, ms)
        return ToolResult(name, args, observation, ms, gated, _parse(observation))

    def address_registry(self):
        """The served streets/localities (reference data, not a traced call)."""
        return self.provider.address_registry()


def _record_call(state: Any, name: str) -> None:
    """One more run of this tool in this call — what `guards` count."""
    tools_state = getattr(state, "tools", None)
    if tools_state is None:  # a bare state in a unit test
        return
    tools_state.calls[name] = tools_state.calls.get(name, 0) + 1
    tools_state.last_at[name] = time.time()


def _refusal(error: str, message: str) -> str:
    return json.dumps({"success": False, "error": error, "message": message}, ensure_ascii=False)


def _guards(state: Any, name: str, spec: Any) -> str | None:
    """The manifest's guards: how many times per call, how soon again, and at what hours.
    A guard is a REFUSAL, not an exception — the engine reads it like any observation and
    the caller never waits on a system that was never going to answer."""
    guards = spec.guards
    tools_state = getattr(state, "tools", None)
    done = tools_state.calls.get(name, 0) if tools_state else 0
    if guards.max_per_call and done >= guards.max_per_call:
        return _refusal(
            "guard_max_per_call",
            f"{name} already ran {done}x in this call (max {guards.max_per_call}).",
        )
    if guards.cooldown_s and tools_state:
        since = time.time() - tools_state.last_at.get(name, 0.0)
        if tools_state.last_at.get(name) and since < guards.cooldown_s:
            return _refusal(
                "guard_cooldown",
                f"{name} ran {round(since)}s ago; it may run again after {guards.cooldown_s}s.",
            )
    if guards.allowed_hours:
        start, end = (int(part) for part in guards.allowed_hours.split("-"))
        hour = time.localtime().tm_hour
        allowed = start <= hour < end if start <= end else (hour >= start or hour < end)
        if not allowed:
            return _refusal(
                "guard_hours",
                f"{name} may only run between {guards.allowed_hours} (now {hour}).",
            )
    return None


def gate(state: Any, rt: Any, name: str, args: dict) -> str | None:
    """
    Deterministic tool-access gate.

    Returns a corrective observation (JSON string) when the tool's manifest does not
    allow this call — otherwise None (the call proceeds). The "no diagnostics before
    identification" / "never act on a guessed id" rules live here rather than in the
    prompt, so a hallucinated `diagnose_connection` cannot fire (observed: customer_id='1'
    on an unidentified caller); how often a tool may run comes from its guards.
    """
    # check_outages must be street-specific. A city-only query returns OTHER
    # streets' outages, which the model then misattributes to the caller
    # (observed). Require a street (area="Miestas, Gatvė") OR a customer_id —
    # the house/apartment is NOT required (street-level check is valid pre-house).
    if name == "check_outages":
        area = (args.get("area") or "").strip()
        if area and "," not in area and not args.get("customer_id"):
            return _refusal(
                "city_only",
                "check_outages needs a street: pass area='City, Street' (not the city "
                "alone) or customer_id. A city-only check returns other streets' outages.",
            )

    spec = manifests.manifest(name)
    if spec is None:
        return None
    blocked = _guards(state, name, spec)
    if blocked is not None:
        return blocked
    if "identified" not in spec.requires:
        return None
    if not state.identity.customer_id:
        return _refusal(
            "not_identified",
            "The caller is not identified yet. First find and confirm the address "
            "(resolve_address) — only then are diagnostics or actions allowed.",
        )
    cid = args.get("customer_id")
    if cid and cid != state.identity.customer_id:
        return _refusal(
            "id_mismatch",
            f"customer_id must be the identified caller's: {state.identity.customer_id}. "
            "Do not use another or a guessed id.",
        )
    return None
