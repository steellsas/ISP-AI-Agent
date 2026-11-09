"""Every fact the CALLER can tell us, in one list (Andrius, 2026-11-06).

The perception pass used to be allowed only the active card's `needs` plus a few built-in
keys, so a ladder fact said out of turn had nowhere to go: eval S9, „Patikrinau, WiFi
įjungtas" while the readiness question was out — the model understood it, but `wifi_on` was
not a key it could write, and the step after it asked the same thing again.

The list is built from the knowledge files, never by hand:

    modules   each `answers` entry is a caller's answer → `fact=value`
    cards     each `needs` entry with the values it declares
    built-in  the evidence keys the reading layer has always known

Telemetry-owned facts are left out: the line tells us those, the caller does not. A new
module or card extends the list by itself.

Collect everything, use by branch: the reading layer may write any fact listed here, and the
engine still takes only what its current step needs — the rest waits in the ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class CatalogFact:
    key: str
    values: set[str] = field(default_factory=set)
    # One line on what the fact is, for the model (the module's goal or the card's question).
    about: str = ""


def _clean(text: str) -> str:
    text = re.sub(r"\{[a-z_]+\}", "device", text or "")
    return " ".join(text.split())[:140]


@lru_cache(maxsize=1)
def client_facts() -> dict[str, CatalogFact]:
    """key -> CatalogFact, for every fact a caller can state."""
    from .contract import cards as catalog
    from .contract import signals
    from .contract.locale import maybe_phrase
    from .perceive.understand import _ALLOWED

    telemetry = set(signals.get())
    out: dict[str, CatalogFact] = {}

    def add(key: str, value: str, about: str = "") -> None:
        if not key or not value or key in telemetry or key.startswith("_"):
            return
        item = out.setdefault(key, CatalogFact(key=key))
        item.values.add(value)
        if about and not item.about:
            item.about = _clean(about)

    for key, values in _ALLOWED.items():
        for value in values:
            add(key, value)
    # The module that PRODUCES a fact describes it best (`reach` for `reachable`, not
    # `wifi_ready`, whose „no" also lands there) — those go first.
    pairs = []
    for spec in catalog.modules().values():
        for stated in (spec.answers or {}).values():
            if "=" in stated:
                key, value = (part.strip() for part in stated.split("=", 1))
                pairs.append((key not in (spec.produces or []), key, value, spec.goal))
    for _later, key, value, goal in sorted(pairs, key=lambda p: p[0]):
        add(key, value, goal)
    for card in catalog.cards().values():
        for key, need in card.needs.items():
            about = ""
            if need.ask:
                try:
                    about = maybe_phrase(need.ask) or ""
                except Exception:  # pragma: no cover - a phrase with params
                    about = ""
            for value in list(need.values) + list(need.answers):
                add(key, value, about)
    return out


def allowed_map() -> dict[str, set[str]]:
    """key -> allowed values, the shape the perception validator takes."""
    return {key: set(item.values) for key, item in client_facts().items()}


def fact_line(key: str, values: set[str]) -> str:
    """One fact for the perception prompt, each value in the caller's language — the SAME
    words the engine says back („restored: yes = „internetas veikia“"). The English goal of a
    module told the model what the step is for, not what the caller says: „Taip, dabar veikia"
    never became `restored` (eval S9, 2026-11-06)."""
    parts = []
    for value in sorted(values):
        words = said_back(key, value)
        parts.append(f"{value} = „{words}“" if words else value)
    line = f"  {key}: " + "; ".join(parts)
    item = client_facts().get(key)
    if item is not None and item.about:
        line += f"  ({item.about})"
    return line


def prompt_listing() -> str:
    """The catalogue as the perception prompt lists it: one line per fact."""
    return "\n".join(fact_line(k, item.values) for k, item in sorted(client_facts().items()))


def said_back(key: str, value: str) -> str | None:
    """The fact said back to the caller, as ONE prepared phrase („Wi-Fi įjungtas").

    Never assembled from a label and a value: that is how „ar galite pasižiūrėti — ar
    teisingai?" was born (finding #56). No phrase — nothing is said back.
    """
    from .contract.locale import phrase_or

    return phrase_or(f"evidence.said_back.{key}.{value}", None)


def hedged(text: str | None) -> bool:
    """Does the caller hedge („lyg ir", „turbūt", „rodos")? Their own doubt — not ours."""
    from .contract.locale import vocab
    from .evidence import _fold

    low = f" {' '.join(re.findall(r'\w+', _fold(text or '')))} "
    return any(f" {_fold(mark)} " in low for mark in vocab("hedge_words"))


# Answers that mean something only to their OWN question: „galite pasižiūrėti dabar" heard out
# of turn is a misreading („Tik viename" became `device_ready=yes`, eval S9 2026-11-06).
ASKED_ONLY = frozenset({"device_ready", "reachable"})

_POLARITY_WORDS = frozenset(
    {"taip", "ne", "jo", "aha", "mhm", "gerai", "tai", "dabar", "nu", "na", "ok", "o"}
)


def content_words(text: str | None) -> str:
    """The utterance without its yes/no and fillers — what the caller added of their own."""
    words = re.findall(r"\w+", (text or "").lower())
    return " ".join(w for w in words if w not in _POLARITY_WORDS)
