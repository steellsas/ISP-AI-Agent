"""
Question registry — the B-wave foundation (Andrius 2026-09-07): a universal
dialogue engine where the LAST question asked has ONE owner, and every caller
turn is first read against THAT question (answered / partial / unclear ->
clarify / deviation -> return to the path).

Step 1 (shadow): the registry MIRRORS reality — question owners fill it,
readers clear it, and the trace shows `question` events. It does not change
behavior yet: routing still runs on the existing flags
(_reopen_confirm_pending, _cannot_now_state, ticket_stage...). Steps 2-4
migrate the identification, ticket and walker questions one owner at a time
until the registry becomes the single routing source and the priority judge
(safety > active clarification > stage owner > side topic).

Owners: "safety" (reopen_confirm, cannot_now...), "ident" (address,
apartment, name, account code), "ticket" (phone, hours), "walker"
(evidence/steps).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Priority order for a multi-signal turn (live P6 2026-09-07: "negaliu
# dabar" + "ne namuose" + an address question in ONE turn) — the lower
# number wins.
OWNER_PRIORITY = {"safety": 0, "ident": 1, "ticket": 2, "walker": 3}


@dataclass
class ActiveQuestion:
    """One asked question: who asked, what for, and which attempt this is."""

    owner: str  # "safety" | "ident" | "ticket" | "walker"
    key: str  # e.g. "reopen_confirm", "cannot_now_clarify", "ticket_phone"
    asks: int = 1  # attempt count for the SAME question (clarify limit)
    data: dict[str, Any] = field(default_factory=dict)  # owner context


def register(engine: Any, owner: str, key: str, **data: Any) -> ActiveQuestion:
    """A question owner declares: THIS question now owns the turn. Re-asking
    the same question bumps the asks counter (feeds the clarify limit)."""
    prev = getattr(engine, "_active_question", None)
    q = ActiveQuestion(owner=owner, key=key, data=data)
    if prev is not None and prev.owner == owner and prev.key == key:
        q.asks = prev.asks + 1
    engine._active_question = q
    engine.tracer.emit("question", owner=owner, key=key, asks=q.asks)
    return q


def active(engine: Any) -> ActiveQuestion | None:
    return getattr(engine, "_active_question", None)


def clear(engine: Any, key: str | None = None) -> None:
    """The answer was read (or the question written off) — clear the entry.
    With `key` given, clears only when exactly that question is active
    (never touches someone else's question)."""
    q = getattr(engine, "_active_question", None)
    if q is None:
        return
    if key is not None and q.key != key:
        return
    engine._active_question = None
    engine.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")


def clear_owner(engine: Any, owner: str) -> None:
    """A whole owner's stage got answered (e.g. identification committed) —
    close its active question, leaving other owners' questions alone."""
    q = getattr(engine, "_active_question", None)
    if q is not None and q.owner == owner:
        engine._active_question = None
        engine.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")
