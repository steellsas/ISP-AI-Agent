"""Telemetry signals as FACTS (wave 3, review finding U).

The provider-side reading used to go straight into a decision tree in code
(`verdict.py::decide`) and come out as one verdict, so a new fault meant a new branch in
Python and the fault cards never took part in the diagnosis at all.

Now every signal becomes a fact of the same shape as anything the caller says — key,
value, source, turn — and what those facts MEAN is declared by the fault cards. The
mapping itself lives in `knowledge/signals.yaml`; this module only reads it.

The values stay raw on purpose (`traffic=none`, not `router_side_ok`): the moment the code
starts interpreting, the interpretation is back in Python (Andrius, 2026-09-22).
"""

from __future__ import annotations

from typing import Any

from .contract import limits
from .contract.schema import SignalMap

ANY = "*"
MISSING = "null"


def facts_from_signals(signals: dict[str, Any] | None) -> dict[str, str]:
    """Every fact this telemetry reading establishes, keyed as the cards name them.

    A signal that is absent yields whatever the map declares for `null` (usually
    `unknown`) — "we did not see it" is itself a fact the cards may rely on, and it must
    never be confused with "we saw that it is fine".
    """
    from .contract import signals as catalog

    if not signals:
        return {}
    out: dict[str, str] = {}
    for key, spec in catalog.get().items():
        value = _read(spec, signals)
        if value is not None:
            out[key] = value
    return out


def _read(spec: SignalMap, signals: dict[str, Any]) -> str | None:
    if spec.derive:
        return DERIVATIONS[spec.derive](signals)
    raw = signals.get(spec.signal) if spec.signal else None
    if spec.present:
        return "yes" if raw not in (None, "", [], {}, False) else "no"
    if spec.above:
        if raw is None:
            return "unknown"
        return (
            spec.above.then if float(raw) > limits.get(spec.above.limit) else spec.above.otherwise
        )
    if spec.map:
        if raw is None:
            return spec.map.get(MISSING, spec.map.get(ANY))
        key = str(raw).lower() if not isinstance(raw, bool) else str(raw).lower()
        return spec.map.get(key, spec.map.get(ANY))
    return None


# --- the readings that compare two signals, or a signal against the clock -------------
# Everything else is a plain map in signals.yaml; each exception is named there.


def _mac_match(signals: dict[str, Any]) -> str:
    """Is the device on the line the one we have on file? A foreign MAC is the whole
    "customer changed the router" fault, so unknown and mismatch must not blur together."""
    observed = (signals.get("observed_mac") or "").lower() or None
    registered = (signals.get("registered_mac") or "").lower() or None
    if observed is None or registered is None:
        return "unknown"
    return "match" if observed == registered else "foreign"


def _neighbours_state(signals: dict[str, Any]) -> str:
    """What the neighbours on the same switch look like — the difference between "this
    flat's line broke" and "the node is down and nobody registered it"."""
    up, down = signals.get("neighbors_up"), signals.get("neighbors_down")
    if up is None and down is None:
        return "unknown"
    if (up or 0) == 0 and (down or 0) > 0:
        return "all_down"
    return "mixed"


DERIVATIONS = {"mac_match": _mac_match, "neighbours_state": _neighbours_state}


def gloss(fact: str, value: str | None) -> str | None:
    """How this fact sounds to a person ("traffic=none" -> "srautas iki routerio
    nevaikšto"). None when the locale does not gloss it — an internal fact is not said out
    loud rather than said badly.
    """
    from .contract.locale import maybe_phrase

    if not value:
        return None
    return maybe_phrase(f"fact.{fact}.{value}")


def summary(facts: dict[str, str], keys) -> str:
    """The glossed facts, in the order given, as one spoken list. This is the "what I see"
    half of a finding: without it the caller has no idea why they are being asked to do
    something (Andrius, 2026-09-22).
    """
    said = [gloss(key, facts.get(key)) for key in keys]
    return ", ".join(part for part in said if part)
