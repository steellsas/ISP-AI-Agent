"""The equipment catalogue from knowledge/v2/equipment/*.yaml (wave 3, P-8).

Reading only: `chain_for` returns the levels that describe a device, least specific first,
so agent/equipment.py can merge them. A type always has a basic level — the validator
refuses a catalogue where it does not.
"""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, EquipmentSpec, KnowledgeError, _read

EQUIPMENT_DIR = KNOWLEDGE_DIR / "v2" / "equipment"


@lru_cache(maxsize=1)
def get() -> dict[str, EquipmentSpec]:
    """Every level of the catalogue, keyed by its id."""
    errors: list[str] = []
    out: dict[str, EquipmentSpec] = {}
    for path in sorted(EQUIPMENT_DIR.glob("*.yaml")):
        spec = _read(path, EquipmentSpec, errors, KNOWLEDGE_DIR)
        if spec is None:
            continue
        if spec.equipment in out:
            errors.append(f"{path.name}: equipment '{spec.equipment}' is declared twice")
        out[spec.equipment] = spec
    if errors:
        raise KnowledgeError(errors)
    return out


def basic(device_type: str) -> EquipmentSpec | None:
    """The level every device of this type falls back to."""
    return next(
        (s for s in get().values() if s.type == device_type and s.extends is None),
        None,
    )


def match(device_type: str, model: str | None) -> EquipmentSpec | None:
    """The most specific level whose `matches` appears in the model string."""
    if not model:
        return None
    said = model.strip().lower()
    hits = [
        s
        for s in get().values()
        if s.type == device_type and any(m.lower() in said for m in s.matches)
    ]
    # A model file is more specific than a family file: the longer chain wins.
    return max(hits, key=lambda s: len(_chain(s)), default=None)


def _chain(spec: EquipmentSpec) -> list[EquipmentSpec]:
    """This level and everything it inherits, least specific first."""
    levels: list[EquipmentSpec] = []
    seen: set[str] = set()
    current: EquipmentSpec | None = spec
    while current is not None and current.equipment not in seen:
        levels.append(current)
        seen.add(current.equipment)
        current = get().get(current.extends) if current.extends else None
    return list(reversed(levels))


def chain_for(device_type: str, model: str | None = None) -> list[EquipmentSpec]:
    """The levels describing this device, least specific first. Falls back to the basic
    level, so the agent always has something to say."""
    specific = match(device_type, model)
    if specific is not None:
        return _chain(specific)
    base = basic(device_type)
    return [base] if base else []


def reload() -> None:
    get.cache_clear()
