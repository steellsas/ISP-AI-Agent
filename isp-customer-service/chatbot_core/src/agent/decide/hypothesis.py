"""Contradictions, and the ONE question that settles them (D-05).

Wave 3 took the belief machine away — the Case holds candidates over facts, so nothing
"activates", "doubts" or "settles" a single hypothesis any more. What remains was never
about a hypothesis: when the caller's words contradict what the call already established,
the engine ASKS ("sakėte X, dabar Y — kaip yra iš tiesų?") instead of choosing silently.
The reading layer and the analyst both use it.
"""

from __future__ import annotations


def doubt(state, rt, kind: str, key: str, before, now, source: str = "client") -> bool:
    """Put the belief in doubt; False when another contradiction is already open."""
    from ..evidence import Contradiction

    if state.diagnosis.contradiction is not None:
        return False
    state.diagnosis.contradiction = Contradiction(
        kind=kind,
        source=source,
        fact_key=key,
        before_value=None if before is None else str(before),
        now_value=None if now is None else str(now),
    )
    rt.tracer.emit("hypothesis", status="doubt", kind=kind, key=key, before=before, now=now)
    return True


def due(state, kind: str):
    """The contradiction of `kind` whose confirm question is due, or None."""
    c = state.diagnosis.contradiction
    return c if c is not None and c.kind == kind and not c.asked else None


def ask(state, rt, kind: str):
    """Mark the due confirm question of `kind` as out (confirming); the contradiction."""
    c = due(state, kind)
    if c is not None:
        c.asked = True
        rt.tracer.emit("hypothesis", status="confirming", kind=kind, key=c.fact_key)
    return c


def answered(state, rt, kind: str):
    """The contradiction of `kind` whose question was out — taken (the belief is active
    again once the answer is read), or None."""
    c = state.diagnosis.contradiction
    if c is None or c.kind != kind or not c.asked:
        return None
    state.diagnosis.contradiction = None
    rt.tracer.emit("hypothesis", status="active", kind=kind, key=c.fact_key)
    return c
