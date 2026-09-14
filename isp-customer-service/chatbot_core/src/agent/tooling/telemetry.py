"""
Telemetry — the one provider-side read of the caller's line (D-08).

snapshot: the first picture — commits verdict, hypothesis and strategy to state.
recheck:  a read-only verification (after a fix, before a close) — returns the
          fresh verdict/signals and never changes state.
Both run diagnose_connection through the gateway.
"""

from __future__ import annotations

from typing import Any, Literal

from .gateway import ToolResult


def telemetry(engine: Any, *, mode: Literal["snapshot", "recheck"], reason: str) -> ToolResult:
    return engine.tools.run(
        engine,
        "diagnose_connection",
        {"customer_id": engine.state.identity.customer_id},
        reason=f"{mode}:{reason}",
        apply=mode == "snapshot",
    )
