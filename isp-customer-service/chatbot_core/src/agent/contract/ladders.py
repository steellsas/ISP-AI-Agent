"""Ladders from knowledge/v2/ladders/*.yaml — runs of steps a card reuses for any device.

A card's solution names one (`- ladder: wifi` with `args: {device: phone}`) and the schema
expands it into the ladder's own steps, so the engine only ever sees module calls.
"""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, KnowledgeError, Ladder, _read

LADDERS_DIR = KNOWLEDGE_DIR / "v2" / "ladders"


@lru_cache(maxsize=1)
def get() -> dict[str, Ladder]:
    errors: list[str] = []
    out: dict[str, Ladder] = {}
    for path in sorted(LADDERS_DIR.glob("*.yaml")):
        spec = _read(path, Ladder, errors, KNOWLEDGE_DIR)
        if spec is None:
            continue
        if spec.ladder in out:
            errors.append(f"{path.name}: ladder '{spec.ladder}' is declared twice")
        out[spec.ladder] = spec
    if errors:
        raise KnowledgeError(errors)
    return out


def reload() -> None:
    get.cache_clear()
