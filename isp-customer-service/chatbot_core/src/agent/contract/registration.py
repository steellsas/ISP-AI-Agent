"""When a ticket is registered — the reasons in `knowledge/registracija.yaml`.

The engine registers only for a reason this file names (Andrius, 2026-10-13: the engine decides,
the speaking model only says what it decided). An unknown reason is a programming error: it
fails loudly instead of registering for a reason nobody wrote down.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from .schema import KNOWLEDGE_DIR, KnowledgeError

FILE = KNOWLEDGE_DIR / "registracija.yaml"


@lru_cache(maxsize=1)
def reasons() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(FILE.read_text(encoding="utf-8")) or {}
    found = data.get("priezastys") or {}
    if not isinstance(found, dict) or not found:
        raise KnowledgeError([f"{FILE.name}: no `priezastys`"])
    return {str(k): dict(v or {}) for k, v in found.items()}


def check(why: str) -> str:
    """`why` itself, when the file names it; raises otherwise."""
    if why not in reasons():
        raise KnowledgeError([f"{FILE.name}: no registration reason '{why}'"])
    return why


def for_the_ticket(why: str | None) -> str:
    """The reason in words for the ticket („gedimo telefonu pašalinti negalima")."""
    return str(reasons().get(why or "", {}).get("tiketui") or "")


def mark(state: Any, why: str) -> None:
    """Record why this call registers — for a registration that does not go through the
    contact dialogue (a hang-up, the stuck ladder, news that registers itself)."""
    state.ticket.reason = check(why)
