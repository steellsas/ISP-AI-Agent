"""Numeric behaviour limits from knowledge/limits.yaml.

`get(name)` returns the file's value; an entry's `env` variable wins when set and
parses as a number. The environment is read on every call — the dashboard changes
some of these variables while the app runs.
"""

from __future__ import annotations

import os
from functools import lru_cache

from .schema import KNOWLEDGE_DIR, KnowledgeError, Limit, Limits, _read

LIMITS_FILE = KNOWLEDGE_DIR / "limits.yaml"


@lru_cache(maxsize=1)
def _limits() -> dict[str, Limit]:
    errors: list[str] = []
    limits = _read(LIMITS_FILE, Limits, errors, KNOWLEDGE_DIR)
    if errors or limits is None:
        raise KnowledgeError(errors)
    return limits.entries()


def get(name: str) -> int | float:
    try:
        spec = _limits()[name]
    except KeyError:
        raise KnowledgeError([f"limits.yaml: no limit '{name}'"]) from None
    raw = os.environ.get(spec.env) if spec.env else None
    if raw is not None:
        try:
            number = float(raw)
        except ValueError:
            return spec.value
        return int(number) if isinstance(spec.value, int) else number
    return spec.value


def names() -> set[str]:
    return set(_limits())


def reload() -> None:
    _limits.cache_clear()
