"""The signal -> fact catalogue from knowledge/signals.yaml (wave 3).

What the telemetry says becomes a fact the cards can reason about; the mapping is data,
so a new signal is a file edit. agent/facts.py does the reading.
"""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, KnowledgeError, SignalMap, Signals, _read

SIGNALS_FILE = KNOWLEDGE_DIR / "signals.yaml"


@lru_cache(maxsize=1)
def _catalogue() -> Signals:
    errors: list[str] = []
    signals = _read(SIGNALS_FILE, Signals, errors, KNOWLEDGE_DIR)
    if errors or signals is None:
        raise KnowledgeError(errors)
    return signals


def get() -> dict[str, SignalMap]:
    """Every fact the telemetry can establish, keyed by fact name."""
    return _catalogue().facts


def probe() -> str | None:
    """The tool that reads these signals — what the engine runs instead of asking."""
    return _catalogue().probe


def reload() -> None:
    _catalogue.cache_clear()
