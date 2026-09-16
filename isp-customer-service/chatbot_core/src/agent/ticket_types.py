"""Ticket types (D-11): what a registered request is, and where it goes.

`knowledge/ticket_types.yaml` declares each type's department and priority; integration
maps them onto the real CRM.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_PATH = Path(__file__).parent / "knowledge" / "ticket_types.yaml"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    from .contract.loader import read_yaml

    data = read_yaml(_PATH) or {}
    types = data.get("ticket_types") if isinstance(data, dict) else None
    return types if isinstance(types, dict) else {}


def reload() -> None:
    _catalog.cache_clear()


def known(ticket_type: str | None) -> bool:
    return bool(ticket_type) and ticket_type in _catalog()


def priority(ticket_type: str | None) -> str:
    return str((_catalog().get(ticket_type or "") or {}).get("priority") or "medium")


def fault_type(verdict: str | None) -> str:
    """The ticket a fault becomes: a fault no pack could explain is `fault_unclear`,
    every other one needs a technician."""
    return "fault_unclear" if verdict == "unclear_fault" else "fault_technician"
