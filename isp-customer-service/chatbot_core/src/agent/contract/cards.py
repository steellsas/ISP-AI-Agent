"""Fault cards v2 and their modules (wave 3).

A card declares when it is a CANDIDATE (`when` / `rules_out`), what would settle it
(`needs`) and how it is fixed (`solution` — modules with arguments). The engine reads
these; nothing about a fault lives in code any more (review findings U, N, AG).

During wave 3 the v2 files live under `knowledge/v2/` beside the v1 packs they replace;
the cut-over commit moves them up and deletes `knowledge/faults/`.
"""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, FaultCard, KnowledgeError, ModuleSpec, _read

CARDS_DIR = KNOWLEDGE_DIR / "v2" / "cards"
MODULES_DIR = KNOWLEDGE_DIR / "v2" / "modules"


def _load(directory, model, key: str) -> dict:
    errors: list[str] = []
    out: dict = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = _read(path, model, errors, KNOWLEDGE_DIR)
        if spec is None:
            continue
        name = getattr(spec, key)
        if name in out:
            errors.append(f"{path.name}: {key} '{name}' is declared twice")
        out[name] = spec
    if errors:
        raise KnowledgeError(errors)
    return out


@lru_cache(maxsize=1)
def cards() -> dict[str, FaultCard]:
    """Every fault card, keyed by fault id."""
    return _load(CARDS_DIR, FaultCard, "fault")


@lru_cache(maxsize=1)
def modules() -> dict[str, ModuleSpec]:
    """Every module a card may call, keyed by module name."""
    return _load(MODULES_DIR, ModuleSpec, "module")


def card(fault: str) -> FaultCard | None:
    return cards().get(fault)


def module(name: str) -> ModuleSpec | None:
    return modules().get(name)


def reload() -> None:
    cards.cache_clear()
    modules.cache_clear()
