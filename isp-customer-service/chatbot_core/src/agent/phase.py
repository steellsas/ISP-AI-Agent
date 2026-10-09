"""The call's phase — SHADOW only (docs/review/STRUKTURA_V3.md, stage 2).

The phase is computed from the state the existing rules leave after every turn and traced as a
`phase` event; nothing reads it to decide. The point is to SEE the call the way v3 will run it
— which phase each turn was in, how long a phase took, and whether a move between phases is one
the v3 table allows — before any rule is moved under a phase owner (stage 3).

    greeting → intake → identify → investigate ⟲ → ticket → closing
"""

from __future__ import annotations

from typing import Any

GREETING, INTAKE, IDENTIFY, INVESTIGATE, TICKET, CLOSING = (
    "greeting",
    "intake",
    "identify",
    "investigate",
    "ticket",
    "closing",
)
PHASES = (GREETING, INTAKE, IDENTIFY, INVESTIGATE, TICKET, CLOSING)

# Moves v3 allows (STRUKTURA_V3 §1.1). Staying in a phase is always allowed. Anything else is
# traced as unexpected — a hint that a rule jumped where no phase owner would.
ALLOWED: dict[str, frozenset[str]] = {
    GREETING: frozenset({INTAKE, IDENTIFY, CLOSING}),
    INTAKE: frozenset({IDENTIFY, INVESTIGATE, TICKET, CLOSING}),
    IDENTIFY: frozenset({INTAKE, INVESTIGATE, TICKET, CLOSING}),
    INVESTIGATE: frozenset({IDENTIFY, TICKET, CLOSING}),
    TICKET: frozenset({INVESTIGATE, CLOSING}),
    CLOSING: frozenset({INVESTIGATE, TICKET}),
}


def phase_of(state: Any) -> str:
    """Which phase the call is in, read from the state the current rules keep."""
    s = state
    if s.closing.case_closed:
        return CLOSING
    if s.ticket.stage and not s.ticket.ticket_id:
        return TICKET
    if not (s.dialog.last_heard or s.intake.heard_utterances):
        return GREETING
    if not s.intake.problem_type:
        return INTAKE
    if not s.identity.customer_id or s.identity.result_pending or s.identity.holder_clarify_open:
        return IDENTIFY
    # News (a debt, an outage, an open ticket) once told IS the ending — v3 merges the outcome
    # into the closing phase. A Case fault is never news (wave 10, S1).
    if (s.diagnosis.news_delivered or s.diagnosis.outage_reported) and not s.case.fault:
        return CLOSING
    return INVESTIGATE


def observe(state: Any, rt: Any) -> None:
    """Record this turn's phase on the state and in the trace (decides nothing)."""
    now = phase_of(state)
    before = state.dialog.phase
    if before == now:
        state.dialog.phase_turns += 1
    else:
        state.dialog.phase_turns = 1
        state.dialog.phase_path.append(now)
    state.dialog.phase = now
    ok = before is None or before == now or now in ALLOWED.get(before, frozenset())
    rt.tracer.emit(
        "phase",
        phase=now,
        prev=before,
        ok=ok,
        turns_in_phase=state.dialog.phase_turns,
    )
