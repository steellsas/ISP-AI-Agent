"""Who actually answers a tool call (wave 2c-5).

A manifest names its adapter; this registry turns that name into something that can run
the call. Two kinds exist:

    in-process   demo_db, rag_local — the local provider the gateway was built with.
                 Called on the calling thread: a local query cannot be cut loose by a
                 timeout, and a worker thread would hold its own SQLite connection open.
    out-of-process  fake (the test seam), and later mcp:<server> / http:<service> — run
                 on a worker thread under the manifest's timeout_s.

Switching a tool to a real system (stage 12) is its manifest's `adapter:` line plus the
adapter registered here. An adapter that is named but not registered fails at STARTUP, so
a premature switch cannot quietly fall back to the demo database.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

# Adapters the gateway's own provider answers, on the calling thread.
INLINE_ADAPTERS = frozenset({"demo_db", "rag_local"})


@dataclass
class FakeAdapter:
    """A system that misbehaves on purpose: slow, broken, or simply empty.

    The demo answers every call in about a millisecond, so without this there is no way to
    see what the agent does when a real CRM takes eight seconds or an NMS refuses the
    connection. Tests program it per tool; nothing else ever selects it, because only a
    manifest that says `adapter: fake` reaches it.
    """

    script: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def program(
        self,
        tool: str,
        *,
        delay: float = 0.0,
        error: str | None = None,
        fail_times: int = 0,
        result: dict[str, Any] | None = None,
    ) -> None:
        """How this tool behaves: how long it takes, whether it breaks (and how often
        before it recovers), and what it returns when it works."""
        self.script[tool] = {
            "delay": delay,
            "error": error,
            "fail_times": fail_times,
            "result": result or {"success": True},
        }

    def reset(self) -> None:
        self.script.clear()
        self.calls.clear()

    def available_tools(self) -> list:
        return []

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((tool_name, dict(arguments)))
        how = self.script.get(tool_name, {})
        if how.get("delay"):
            time.sleep(how["delay"])
        if how.get("error"):
            attempts = sum(1 for name, _a in self.calls if name == tool_name)
            if not how.get("fail_times") or attempts <= how["fail_times"]:
                raise RuntimeError(how["error"])
        return json.dumps(how.get("result", {"success": True}), ensure_ascii=False)


_FAKE = FakeAdapter()
_REGISTRY: dict[str, Any] = {"fake": _FAKE}


def fake() -> FakeAdapter:
    """The fake adapter tests program."""
    return _FAKE


def register(name: str, adapter: Any) -> None:
    """Make `name` answerable (an MCP client, an HTTP service, a stub)."""
    _REGISTRY[name] = adapter


def get(name: str) -> Any | None:
    return _REGISTRY.get(name)


def known() -> frozenset[str]:
    """Every adapter name a manifest may use today."""
    return INLINE_ADAPTERS | frozenset(_REGISTRY)
