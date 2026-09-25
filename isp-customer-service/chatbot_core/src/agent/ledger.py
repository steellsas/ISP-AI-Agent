"""The facts of a call, in one flat view (wave 3d).

`case.py` is a pure function of facts and `modules.py` is a pure function of a module call.
This is the only place that knows about the call's state, so the reasoning stays testable
as a table.

Two things feed the ledger:

    telemetry   a probe's signals, read through knowledge/signals.yaml
    the caller  what they told us, written as the fault cards name it

Telemetry is the arbiter (D-07): a reading overwrites what words established, never the
other way round. What we could not get at all is recorded too — a question the caller could
not answer is a fact about the call, and it stops the engine asking it forever.
"""

from __future__ import annotations

from typing import Any

from .contract.locale import maybe_phrase  # noqa: F401  (kept for the engine's use)
from .facts import facts_from_signals

TELEMETRY = "telemetry"
CLIENT = "client"
# Nobody could tell us and the card said what to carry on with (`assume`): a fact like any
# other for the cards, but its source is named so the caller and the ticket hear the truth.
ASSUMED = "assumed"


def facts_of(state: Any) -> dict[str, str]:
    """Everything the cards may reason over right now."""
    return dict(state.case.facts)


def record_telemetry(state: Any, rt: Any, signals: dict[str, Any] | None) -> dict[str, str]:
    """Fold a probe's reading into the ledger. Returns what changed, so the engine can say
    what it just learned instead of repeating the whole picture."""
    read = facts_from_signals(signals)
    changed = {k: v for k, v in read.items() if state.case.facts.get(k) != v}
    state.case.facts.update(read)
    # A fact we can now see is no longer a fact we failed to get.
    state.case.unavailable = [f for f in state.case.unavailable if f not in read]
    # A fresh reading is what a verification was waiting for.
    state.case.awaiting_probe = False
    if changed and rt is not None:
        rt.tracer.emit("facts", source=TELEMETRY, changed=changed)
    return changed


def record_client(state: Any, rt: Any, fact: str, value: str | None) -> bool:
    """What the caller said. A value that contradicts TELEMETRY is not written — the line
    is not a matter of opinion — and the engine asks about the difference instead."""
    if not value:
        return False
    known = state.case.facts.get(fact)
    if known == value:
        return False
    if fact in facts_from_signals(_last_signals(state)):
        # A telemetry-owned fact: the caller's word does not overwrite the line.
        if rt is not None:
            rt.tracer.emit("facts", source=CLIENT, refused=fact, said=value, seen=known)
        return False
    state.case.facts[fact] = value
    state.case.unavailable = [f for f in state.case.unavailable if f != fact]
    if rt is not None:
        rt.tracer.emit("facts", source=CLIENT, changed={fact: value})
    return True


def record_assumed(state: Any, rt: Any, fact: str, value: str) -> bool:
    """What we carry on with when the caller could not tell us (the card's `assume`).

    It is written like any other fact so the cards can reason over it, but its SOURCE is the
    assumption — the call record and the ticket say so, and the caller hears it out loud. The
    line still wins: a fact telemetry owns is never assumed.
    """
    if not fact or not value or fact in state.case.facts:
        return False
    if fact in facts_from_signals(_last_signals(state)):
        return False
    state.case.facts[fact] = value
    state.case.assumed[fact] = value
    if rt is not None:
        rt.tracer.emit("facts", source=ASSUMED, changed={fact: value})
    return True


def record_unavailable(state: Any, rt: Any, fact: str) -> None:
    """We tried and could not get it. The engine will not choose this dead end again."""
    if fact and fact not in state.case.unavailable:
        state.case.unavailable.append(fact)
        if rt is not None:
            rt.tracer.emit("facts", unavailable=fact)


def unavailable(state: Any) -> frozenset[str]:
    return frozenset(state.case.unavailable)


def _last_signals(state: Any) -> dict[str, Any]:
    return ((state.diagnosis.verdicts or {}).get("network") or {}).get("signals") or {}


def mirror_evidence(state: Any, rt: Any) -> dict[str, str]:
    """Copy what the evidence READER accepted into the case ledger (wave 3f).

    The reading layer is unchanged — perception, the keyword extractor, the conflict
    clarification and the "done without a result" guard all carry live fixes — so the facts
    it settles are mirrored here rather than read a second time. Telemetry still wins:
    `record_client` refuses to overwrite what the line says.
    """
    from .evidence import UNKNOWN

    changed: dict[str, str] = {}
    for fact, entry in (state.diagnosis.evidence or {}).items():
        value = entry.get("value")
        if not value or value == UNKNOWN or entry.get("conflict"):
            continue  # a value in doubt is not a fact yet: the clarify question settles it
        if record_client(state, rt, fact, str(value)):
            changed[fact] = str(value)
        for name, same in _same_news(fact, str(value)):
            if record_client(state, rt, name, same):
                changed[name] = same
    return changed


def _same_news(fact: str, value: str) -> list[tuple[str, str]]:
    """The v2 facts that carry the same news as this reader key (a module's `also`)."""
    from .contract import cards as catalog

    out: list[tuple[str, str]] = []
    for spec in catalog.modules().values():
        mapped = (spec.also.get(fact) or {}).get(value)
        if mapped and spec.produces:
            out.append((spec.produces[0], mapped))
    return out
