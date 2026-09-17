"""
Trace helpers — the decision-shaped events a call review reads ("why did the
agent do X"). Pure functions over the tracer and the call state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def trace_note(tracer: Any, state: Any, where: str, detail: str, level: str = "warn") -> None:
    """Record a behaviour-affecting failure/fallback INTO the trace (not only the
    console log), stamped with the current state (node/step/awaiting), so a call
    review shows WHY the agent behaved as it did — a swallowed classifier/solver/tool
    error no longer disappears from the JSONL. Best-effort; never raises."""
    try:
        r = state.resolution.procedure or {}
        tracer.emit(
            "error",
            level=level,
            where=where,
            detail=(detail or "")[:300],
            node=state.turn.active_node,
            step=r.get("step"),
            awaiting=state.dialog.awaiting,
        )
    except Exception:  # pragma: no cover - tracing must never break the turn
        pass


def trace_tool_result(tracer: Any, name: str, observation: str, ms: int | None = None) -> None:
    """Emit a tool_result event (+ a dedicated verdict event for diagnoses).

    Keeps the trace small: a boolean ok + a few key fields + how long the
    tool took (ms) — needed to know which tool to overlap/mask. The verdict
    is its own event type because "why the agent acted" is the most valuable
    thing when debugging.
    """
    try:
        data = json.loads(observation)
    except (json.JSONDecodeError, TypeError):
        tracer.emit("tool_result", name=name, ok=None, ms=ms, summary="<non-json>")
        return

    ok = data.get("success")
    summary: dict[str, Any] = {}
    for key in ("customer_id", "ticket_id", "outcome"):
        if data.get(key):
            summary[key] = data[key]
    if not ok and data.get("error"):
        summary["error"] = data["error"]
    # resolve_address: surface the per-level hint (drives the next question).
    if name == "resolve_address" and data.get("hint"):
        summary["hint"] = data["hint"]

    tracer.emit("tool_result", name=name, ok=ok, ms=ms, summary=summary or None)

    # diagnose_connection carries the verdict -> its own event.
    verdict = data.get("verdict") if isinstance(data, dict) else None
    if verdict:
        tracer.emit(
            "verdict",
            side=verdict.get("side"),
            group=verdict.get("group"),
            action=verdict.get("action"),
            reason=verdict.get("reason"),
        )


def emit_decision(tracer: Any, state: Any, before: str | None) -> None:
    """One line per strategy turn: what the caller's turn was read as, where the
    walker went (or that it HELD), and the live hypothesis. This is the 'why' the
    raw reply never showed — e.g. step=None means no strategy is active at all."""
    s = state
    r = s.resolution.procedure
    after = r.get("step") if r else None
    if before is None and after is None:
        return  # no strategy in play — nothing to explain
    if s.closing.case_closed:
        action, dest = "close", s.closing.closed_reason
    elif after == before:
        action, dest = "hold", after
    else:
        action, dest = "advance", after
    h = s.diagnosis.hypothesis or {}
    tracer.emit(
        "decision",
        intent=s.dialog.last_intent or None,
        awaiting=s.dialog.awaiting,
        action=action,
        from_step=before,
        to=dest,
        hypothesis=h.get("cause"),
        hyp_status=h.get("status"),
    )


def emit_case(tracer: Any, state: Any) -> None:
    """Emit a compact case-state snapshot to the TRACE (for review) — NOT into
    the LLM context. The lean current-truth the model reads is the facts block;
    the full running summary / history stays in the trace + DB (§12.7)."""
    s = state
    diag = (
        "; ".join(
            f"{dom}:{f.get('group')}/{f.get('reason')}" for dom, f in s.diagnosis.verdicts.items()
        )
        or None
    )
    if not (s.intake.problem_type or s.identity.customer_id or diag or s.intake.symptoms):
        return
    r = s.resolution.procedure or {}
    h = s.diagnosis.hypothesis or {}
    tracer.emit(
        "case",
        problem=s.intake.problem_type,
        customer_id=s.identity.customer_id,
        address=s.identity.customer_address,
        symptoms=(", ".join(f"{k}={v}" for k, v in s.intake.symptoms.items()) or None),
        diagnosis=diag,
        # Decision state — the "where are we / why" that a raw reply hides.
        step=r.get("step"),
        awaiting=s.dialog.awaiting,
        clarity=s.dialog.clarity_level if s.dialog.clarity_level != "standard" else None,
        hypothesis=(f"{h.get('cause')}:{h.get('status')}" if h else None),
    )


def tools_called_this_session(tracer: Any) -> list[str]:
    """Tool names actually executed this call, read from the session's own trace
    (single source of truth; append-only, safe to read at end)."""
    path = getattr(tracer, "path", None)
    if not path:
        return []
    seen: list[str] = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("type") == "tool_call" and e.get("name") and e["name"] not in seen:
                seen.append(e["name"])
    except Exception:  # pragma: no cover - best-effort; the summary still emits
        pass
    return seen
