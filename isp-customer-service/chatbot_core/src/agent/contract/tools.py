"""The tool manifests from knowledge/tools/*.yaml (P-7).

One file per tool: what it can do (capability), which adapter answers it, who may call
it, its guards and timeout, and what happens when it does not answer. The engine reads
the manifest — never the implementation — so switching a tool to a real system (stage 12)
is the `adapter:` line.
"""

from __future__ import annotations

from functools import lru_cache

from .schema import KNOWLEDGE_DIR, KnowledgeError, ToolManifest, _read

TOOLS_DIR = KNOWLEDGE_DIR / "tools"


@lru_cache(maxsize=1)
def get() -> dict[str, ToolManifest]:
    """Every manifest, keyed by tool name."""
    errors: list[str] = []
    out: dict[str, ToolManifest] = {}
    for path in sorted(TOOLS_DIR.glob("*.yaml")):
        manifest = _read(path, ToolManifest, errors, KNOWLEDGE_DIR)
        if manifest is not None:
            out[manifest.tool] = manifest
    if errors:
        raise KnowledgeError(errors)
    return out


def manifest(name: str) -> ToolManifest | None:
    """The tool's contract, or None for a tool that has no manifest yet."""
    return get().get(name)


def names() -> tuple[str, ...]:
    return tuple(sorted(get()))


def reload() -> None:
    get.cache_clear()
