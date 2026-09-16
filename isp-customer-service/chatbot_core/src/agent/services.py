"""The customer's services and what depends on what (D-10).

`knowledge/services.yaml` lists the services, their technologies and the dependencies
(IPTV works only when the internet does). The customer's own profile comes from the CRM
plans at identification (`identity.service_profile`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_SERVICES_PATH = Path(__file__).parent / "knowledge" / "services.yaml"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    from .contract.loader import read_yaml

    data = read_yaml(_SERVICES_PATH) or {}
    return data if isinstance(data, dict) else {}


def reload() -> None:
    _catalog.cache_clear()


def depends_on(service: str | None, technology: str | None) -> str | None:
    """The service this one needs to work (tv over iptv -> internet), or None."""
    for dep in _catalog().get("dependencies") or []:
        if dep.get("service") == service and dep.get("technology") == technology:
            return dep.get("depends_on")
    return None


def subscribed(profile: list[dict[str, Any]] | None, service: str | None) -> dict[str, Any] | None:
    """The customer's active plan for `service`, or None when they do not have it."""
    for plan in profile or []:
        if plan.get("type") == service:
            return plan
    return None
