"""
Question registry — the B-wave foundation (Andrius 2026-09-07): a universal
dialogue engine where the LAST question asked has ONE owner, and every caller
turn is first read against THAT question (answered / partial / unclear ->
clarify / deviation -> return to the path).

Step 1 (shadow): the registry MIRRORS reality — question owners fill it,
readers clear it, and the trace shows `question` events. It does not change
behavior yet: routing still runs on the existing flags
(identity.reopen_confirm_utterance, dialog.cannot_now_state, ticket.stage...). Steps 2-4
migrate the identification, ticket and walker questions one owner at a time
until the registry becomes the single routing source and the priority judge
(safety > active clarification > stage owner > side topic).

Owners: "safety" (reopen_confirm, cannot_now...), "ident" (address,
apartment, name, account code), "ticket" (phone, hours), "walker"
(evidence/steps).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Priority order for a multi-signal turn (live P6 2026-09-07: "negaliu
# dabar" + "ne namuose" + an address question in ONE turn) — the lower
# number wins.
OWNER_PRIORITY = {"safety": 0, "ident": 1, "ticket": 2, "walker": 3}


class ActiveQuestion(BaseModel):
    """One asked question: who asked, what for, and which attempt this is."""

    owner: str  # "safety" | "ident" | "ticket" | "walker"
    key: str  # e.g. "reopen_confirm", "cannot_now_clarify", "ticket_phone"
    asks: int = 1  # attempt count for the SAME question (clarify limit)
    data: dict[str, Any] = Field(default_factory=dict)  # owner context


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


_PACK_CANNOT_NOW_SUFFIXES = ("_ability", "_locate", "_homework")


def pack_owns_cannot_now(state: Any, rt: Any) -> bool:
    """File convention (P-C, 2026-09-08): a strategy step named *_ability /
    *_locate / *_homework IS the pack's own cannot-now handling ("can you get
    to the router now?"). While such a step's question is active, the generic
    cannot-now ladder and its head shield stand down — the walker routes the
    answer per the pack file."""
    q = state.dialog.active_question
    return q is not None and q.key.startswith("step:") and q.key.endswith(_PACK_CANNOT_NOW_SUFFIXES)


def clear_owner(state: Any, rt: Any, owner: str) -> None:
    """A whole owner's stage got answered (e.g. identification committed) —
    close its active question, leaving other owners' questions alone."""
    q = state.dialog.active_question
    if q is not None and q.owner == owner:
        state.dialog.active_question = None
        rt.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")
