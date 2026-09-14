"""
LocalToolProvider — the in-process tool implementations (agent/tools.py)
behind the ToolProvider port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.ports.tools import ToolSpec

# Engine-only tools, not offered to the LLM. The simulations reflect the caller's
# physical actions on the seeded demo line (callers guard them with SIMULATE_*).
ENGINE_TOOLS = (
    "append_ticket_note",
    "simulate_router_reboot",
    "simulate_bridge_connect",
    "simulate_bridge_disconnect",
)


@dataclass(frozen=True)
class AddressRegistry:
    """The served streets and localities, for deterministic address reading."""

    streets: list[str]  # "Name g." (with the street type)
    street_names: list[str]  # bare names
    localities: list[str]


class LocalToolProvider:
    """Runs the tools as local Python functions against the demo database."""

    def __init__(self):
        self._registry: AddressRegistry | None = None

    def available_tools(self) -> list[ToolSpec]:
        from ..tools import REAL_TOOLS

        return [ToolSpec(t.name, t.description, t.parameters) for t in REAL_TOOLS]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        from .. import tools

        if tool_name in ENGINE_TOOLS:
            result = getattr(tools, tool_name)(**arguments)
            return json.dumps(result, ensure_ascii=False)
        return tools.execute_tool(tool_name, arguments)

    def address_registry(self) -> AddressRegistry:
        """Loaded once per provider (the registry does not change during a call)."""
        if self._registry is None:
            from ..tools import get_db

            with get_db().cursor() as cursor:
                cursor.execute("SELECT street_name, street_type, city FROM streets")
                rows = [dict(r) for r in cursor.fetchall()]
            self._registry = AddressRegistry(
                streets=[f"{r['street_name']} {r['street_type'] or 'g.'}".strip() for r in rows],
                street_names=sorted({str(r["street_name"]) for r in rows if r["street_name"]}),
                localities=sorted({r["city"] for r in rows}),
            )
        return self._registry
