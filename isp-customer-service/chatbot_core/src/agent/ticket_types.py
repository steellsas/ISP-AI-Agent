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
    _by_verdict.cache_clear()
    _by_reason.cache_clear()


def known(ticket_type: str | None) -> bool:
    return bool(ticket_type) and ticket_type in _catalog()


def priority(ticket_type: str | None) -> str:
    return str((_catalog().get(ticket_type or "") or {}).get("priority") or "medium")


def department(ticket_type: str | None) -> str:
    return str((_catalog().get(ticket_type or "") or {}).get("department") or "")


def for_call(cause: str | None, reason: str | None) -> str:
    """The ticket this call's fault registration becomes: the reason first (an unfinished
    call is reviewed by a person and called back, whatever the line showed — Andrius,
    2026-10-22), then the fault."""
    mapped = _by_reason().get(reason or "")
    if mapped and known(str(mapped)):
        return str(mapped)
    return fault_type(cause)


def callback_only(cause: str | None, reason: str | None) -> bool:
    """No technician on the way: a person reviews the call and phones back."""
    return for_call(cause, reason) == "call_unfinished"


def fault_type(verdict: str | None) -> str:
    """The ticket a fault becomes.

    A fault no card could explain is `fault_unclear`; a verdict the catalogue maps by name
    gets that type (a dead router is an EQUIPMENT REPLACEMENT, and the technician has to
    know before loading the van — Andrius, 2026-09-30); everything else needs a technician.
    """
    if verdict == "unclear_fault":
        return "fault_unclear"
    mapped = _by_verdict().get(verdict or "")
    return str(mapped) if mapped and known(str(mapped)) else "fault_technician"


@lru_cache(maxsize=1)
def _by_verdict() -> dict[str, str]:
    from .contract.loader import read_yaml

    data = read_yaml(_PATH) or {}
    mapping = data.get("by_verdict") if isinstance(data, dict) else None
    return mapping if isinstance(mapping, dict) else {}


@lru_cache(maxsize=1)
def _by_reason() -> dict[str, str]:
    from .contract.loader import read_yaml

    data = read_yaml(_PATH) or {}
    mapping = data.get("by_reason") if isinstance(data, dict) else None
    return mapping if isinstance(mapping, dict) else {}
