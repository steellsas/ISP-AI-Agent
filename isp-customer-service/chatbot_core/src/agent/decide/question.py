"""
The active question — the last question asked has ONE owner, and every caller turn is
first read against it (answered / partial / unclear -> clarify / deviation -> return to
the path). Question owners register it, readers close it; the decide rules read it for
precedence (safety > identification > ticket > procedure).

Owners: "safety" (reopen_confirm, cannot_now...), "ident" (address, apartment, name,
account code), "ticket" (phone, hours), "walker" (the procedure's evidence and steps).
"""

from __future__ import annotations

from typing import Any

from ..graph_v2.state import ActiveQuestion

# Priority order for a multi-signal turn (live P6 2026-09-07: "negaliu
# dabar" + "ne namuose" + an address question in ONE turn) — the lower
# number wins.
OWNER_PRIORITY = {"safety": 0, "ident": 1, "ticket": 2, "walker": 3}


def register(state: Any, rt: Any, owner: str, key: str, **data: Any) -> ActiveQuestion:
    """A question owner declares: THIS question now owns the turn. Re-asking
    the same question bumps the asks counter (feeds the clarify limit)."""
    prev = state.dialog.active_question
    q = ActiveQuestion(owner=owner, key=key, data=data)
    if prev is not None and prev.owner == owner and prev.key == key:
        q.asks = prev.asks + 1
    state.dialog.active_question = q
    rt.tracer.emit("question", owner=owner, key=key, asks=q.asks)
    return q


def active(state: Any, rt: Any) -> ActiveQuestion | None:
    return state.dialog.active_question


def clear(state: Any, rt: Any, key: str | None = None) -> None:
    """The answer was read (or the question written off) — clear the entry.
    With `key` given, clears only when exactly that question is active
    (never touches someone else's question)."""
    q = state.dialog.active_question
    if q is None:
        return
    if key is not None and q.key != key:
        return
    state.dialog.active_question = None
    rt.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")


def clear_owner(state: Any, rt: Any, owner: str) -> None:
    """A whole owner's stage got answered (e.g. identification committed) —
    close its active question, leaving other owners' questions alone."""
    q = state.dialog.active_question
    if q is not None and q.owner == owner:
        state.dialog.active_question = None
        rt.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")
