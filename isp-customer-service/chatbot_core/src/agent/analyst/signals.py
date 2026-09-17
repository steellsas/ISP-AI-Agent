"""What the analyst may say — a closed set of typed signals (D-06).

The analyst reads the whole call and reports observations; it never writes a fact,
never changes the hypothesis and never speaks. Each signal is a claim the engine
decides what to do with:

  contradiction     a ledger fact clashes with what the caller keeps saying
  already_answered  the caller already answered the fact the engine is about to ask
  secondary_problem another complaint was mentioned in passing
  off_topic         the last answers do not relate to the active question
  frustration       the caller is losing patience (tone only)
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

SignalType = Literal[
    "contradiction",
    "already_answered",
    "secondary_problem",
    "off_topic",
    "frustration",
]


class Signal(BaseModel):
    """One observation about the call, tied to the turn it was read on."""

    type: SignalType
    # The evidence key the signal is about (contradiction / already_answered).
    fact_key: str | None = None
    # What the caller actually said — quoted back to them, never invented.
    quote: str | None = None
    # The value the caller's words imply (already_answered / contradiction).
    value: str | None = None
    confidence: float = 0.0
    # The turn the analyst read; a signal that arrives after the next turn started is
    # stale and is dropped (the async read races the caller).
    turn_index: int = 0


def parse(raw: str | None, turn_index: int) -> list[Signal]:
    """Signals from the analyst's JSON reply — anything malformed is dropped, because a
    sensor hiccup must never break a call."""
    from ..contract import limits

    data = _loads(raw)
    if not isinstance(data, dict):
        return []
    out: list[Signal] = []
    for item in data.get("signals") or []:
        if not isinstance(item, dict):
            continue
        try:
            signal = Signal(**{**item, "turn_index": turn_index})
        except ValidationError:
            continue
        if signal.confidence < limits.get("analyst_confidence_floor"):
            continue
        out.append(signal)
    return out[: limits.get("analyst_signals_max")]


def _loads(raw: str | None):
    text = (raw or "").strip()
    if text.startswith("```"):  # a fenced block from a chatty model
        text = text.strip("`")
        text = text[text.index("{") :] if "{" in text else text
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


class AnalystRead(BaseModel):
    """The analyst's whole answer (the schema the prompt asks for)."""

    signals: list[Signal] = Field(default_factory=list)
