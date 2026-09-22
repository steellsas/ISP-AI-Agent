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
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any

from src.ports.tools import ToolProvider

from ..contract import limits
from ..contract import tools as manifests
from ..trace import trace_tool_result

logger = logging.getLogger(__name__)

# A call that can hang on a NETWORK runs on a worker thread, so the manifest's timeout_s
# can cut it loose; the abandoned thread is the price. In-process adapters are called
# inline: a local query cannot be interrupted anyway, and every worker thread would hold
# its own (thread-local) SQLite connection open for the life of the process — which is how
# the eval's between-scenario DB rebuild started failing with WinError 32.
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool")
# Adapters that answer in-process (no timeout, no thread). `fake` is deliberately NOT here:
# it is the seam that exercises the slow and broken paths in tests.
INLINE_ADAPTERS = frozenset({"demo_db", "rag_local"})
# What may be retried after a TIMEOUT: a read-only lookup is safe to repeat, a mutation is
# not — it may have landed on the line already.
READ_ONLY_CAPABILITIES = frozenset({"probe", "crm", "outages", "knowledge", "simulate"})

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
            _record_call(state, name)  # the adapter is about to run: an action may land
            observation, ms = self._execute(state, rt, spec, name, args)
            gated = False
        if apply:
            from ..execute.observe import update_state_from_observation

            update_state_from_observation(state, rt, name, observation)
        trace_tool_result(rt.tracer, name, observation, ms)
        return ToolResult(name, args, observation, ms, gated, _parse(observation))

    def _execute(
        self, state: Any, rt: Any, spec: Any, name: str, args: dict[str, Any]
    ) -> tuple[str, int]:
        """Run the adapter under its manifest and return (observation, ms).

        A tool that does not answer — a timeout on a remote adapter, or an adapter that
        broke — returns a FAILURE OBSERVATION carrying the manifest's plan (the capability,
        the say_key the caller hears, the `fallback` the engine acts on), so a dead system
        never hangs a call (review finding W: in the demo every tool answers in ~1 ms, so
        this path was never exercised). Retries are asymmetric: a read-only lookup may be
        repeated after a timeout, a mutation may not — it may have landed already.
        """
        if spec is None:  # a tool with no manifest yet: exactly as before
            started = time.perf_counter()
            return self.provider.execute(name, args), _ms_since(started)

        inline = spec.adapter in INLINE_ADAPTERS
        attempts = 1 + spec.retries
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                if inline:
                    observation = self.provider.execute(name, args)
                else:
                    future: Future[str] = _POOL.submit(self.provider.execute, name, args)
                    observation = future.result(timeout=spec.timeout_s)
            except FutureTimeout:
                retry = attempt < attempts and spec.capability in READ_ONLY_CAPABILITIES
                rt.tracer.emit(
                    "tool_timeout",
                    name=name,
                    capability=spec.capability,
                    adapter=spec.adapter,
                    timeout_s=spec.timeout_s,
                    attempt=attempt,
                    retrying=retry,
                    alert=spec.on_failure.alert,
                )
                if retry:
                    continue
                message = f"{name} did not answer in {spec.timeout_s}s"
                return _failed(spec, name, "tool_timeout", message), _ms_since(started)
            except Exception as e:  # the adapter itself broke
                logger.error(f"[TOOL] {name} failed on {spec.adapter}: {e}")
                rt.tracer.emit(
                    "tool_error",
                    name=name,
                    capability=spec.capability,
                    adapter=spec.adapter,
                    error=str(e)[:200],
                    attempt=attempt,
                    retrying=attempt < attempts,
                    alert=spec.on_failure.alert,
                )
                if attempt < attempts:
                    continue
                return _failed(spec, name, "tool_error", str(e)[:200]), _ms_since(started)
            ms = _ms_since(started)
            _trace_slow(rt, spec, name, ms)
            return observation, ms
        raise AssertionError("unreachable")  # pragma: no cover

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


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000.0)


def _trace_slow(rt: Any, spec: Any, name: str, ms: int) -> None:
    """Measured first (P-5): how often a real caller would be left waiting in silence,
    and which line the tool's manifest says to fill it with."""
    if spec is not None and spec.filler_key and ms >= limits.get("tool_slow_ms"):
        rt.tracer.emit("tool_slow", name=name, ms=ms, filler_key=spec.filler_key)


def _refusal(error: str, message: str) -> str:
    return json.dumps({"success": False, "error": error, "message": message}, ensure_ascii=False)


def _failed(spec: Any, name: str, error: str, message: str) -> str:
    """The observation for a tool that did not answer. It carries the manifest's PLAN —
    what the caller hears and which way the call goes on — so the engine never has to
    guess (2c-4 turns `fallback` into the planned action)."""
    return json.dumps(
        {
            "success": False,
            "error": error,
            "tool": name,
            "capability": spec.capability,
            "fallback": spec.on_failure.fallback,
            "say_key": spec.on_failure.say_key,
            "alert": spec.on_failure.alert,
            "message": message,
        },
        ensure_ascii=False,
    )


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
