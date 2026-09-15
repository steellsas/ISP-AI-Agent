"""Business policies from knowledge/policies.yaml (what the agent must not do, and
which tools need an identified caller). Content is filled with the owner; the file
starts with what the code enforced before."""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, KnowledgeError, Policies, _read

POLICIES_FILE = KNOWLEDGE_DIR / "policies.yaml"


@lru_cache(maxsize=1)
def get() -> Policies:
    errors: list[str] = []
    policies = _read(POLICIES_FILE, Policies, errors, KNOWLEDGE_DIR)
    if errors or policies is None:
        raise KnowledgeError(errors)
    return policies


def reload() -> None:
    get.cache_clear()
