"""
ToolGateway — the ONE place a tool call happens.

run(): trace `tool_call` (with the caller's reason) → deterministic access gate
→ provider call → state update from the observation → trace `tool_result`.
Callers get a ToolResult; the observation stays the tool's JSON string.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.ports.tools import ToolProvider

from ..contract import policies
from ..contract.locale import phrase_or
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
        rt.tracer.emit("tool_call", name=name, args=args, reason=reason)
        refusal = gate(state, rt, name, args)
        if refusal is not None:
            observation, ms, gated = refusal, 0, True
        else:
            started = time.perf_counter()
            observation = self.provider.execute(name, args)
            ms, gated = round((time.perf_counter() - started) * 1000.0), False
        if apply:
            from ..execute.observe import update_state_from_observation

            update_state_from_observation(state, rt, name, observation)
        trace_tool_result(rt.tracer, name, observation, ms)
        return ToolResult(name, args, observation, ms, gated, _parse(observation))

    def address_registry(self):
        """The served streets/localities (reference data, not a traced call)."""
        return self.provider.address_registry()


def gate(state: Any, rt: Any, name: str, args: dict) -> str | None:
    """
    Deterministic tool-access gate.

    Returns a corrective observation (JSON string) when a technical tool is
    called before identification, or with a customer_id that is not the
    identified one — otherwise None (the call proceeds). This moves the "no
    diagnostics before identification" / "never act on a guessed id" rules
    out of the prompt and into code, so a hallucinated `diagnose_connection`
    cannot fire (observed: customer_id='1' on an unidentified caller).
    """
    from ..execute.diagnosis import fresh_diagnose_reason

    # check_outages must be street-specific. A city-only query returns OTHER
    # streets' outages, which the model then misattributes to the caller
    # (observed). Require a street (area="Miestas, Gatvė") OR a customer_id —
    # the house/apartment is NOT required (street-level check is valid pre-house).
    if name == "check_outages":
        area = (args.get("area") or "").strip()
        if area and "," not in area and not args.get("customer_id"):
            return json.dumps(
                {
                    "success": False,
                    "error": "city_only",
                    "message": (
                        "check_outages needs a street: pass area='City, "
                        "Street' (not the city alone) or customer_id. A city-only "
                        "check returns other streets' outages."
                    ),
                },
                ensure_ascii=False,
            )
        return None

    # close_case: reason-specific backstop so an over-eager model can't end the
    # call prematurely. "resolved" needs an identified customer; "outage" needs
    # an outage to have actually been reported.
    if name == "close_case":
        reason = args.get("reason", "resolved")
        if reason == "resolved":
            if not state.identity.customer_id:
                return json.dumps(
                    {
                        "success": False,
                        "error": "not_identified",
                        "message": "Cannot close as 'resolved' before the caller is identified.",
                    },
                    ensure_ascii=False,
                )
            # Verify-gate: telemetry is the source of truth. If a fresh
            # diagnose still shows the line fault, the fix has NOT taken —
            # block "resolved" so the agent can't close on the caller's word
            # (observed: B6 closed as resolved without ever binding the MAC).
            reason_now = fresh_diagnose_reason(state, rt)
            from ..faults import verdict_flag

            if verdict_flag(reason_now, "unresolved_after_fix"):
                gloss = phrase_or(f"verdict.{reason_now}.gloss", reason_now)
                return json.dumps(
                    {
                        "success": False,
                        "error": "not_fixed",
                        "message": (
                            f"Telemetry still shows the fault ({gloss}) — NOT fixed yet, "
                            "do not close as 'resolved'. Take the needed action (e.g. "
                            "update_mac + reset_port) and re-run the diagnostics."
                        ),
                    },
                    ensure_ascii=False,
                )
        if reason == "outage" and not state.diagnosis.outage_reported:
            return json.dumps(
                {
                    "success": False,
                    "error": "no_outage",
                    "message": (
                        "close_case(reason='outage') is allowed only after "
                        "check_outages confirmed an active outage."
                    ),
                },
                ensure_ascii=False,
            )
        return None

    if name not in policies.get().identified_customer_required:
        return None
    if not state.identity.customer_id:
        return json.dumps(
            {
                "success": False,
                "error": "not_identified",
                "message": (
                    "The caller is not identified yet. First find and confirm the "
                    "address (resolve_address) — only then are diagnostics or actions allowed."
                ),
            }
        )
    cid = args.get("customer_id")
    if cid and cid != state.identity.customer_id:
        return json.dumps(
            {
                "success": False,
                "error": "id_mismatch",
                "message": (
                    f"customer_id must be the identified caller's: "
                    f"{state.identity.customer_id}. Do not use another or a guessed id."
                ),
            }
        )
    return None
