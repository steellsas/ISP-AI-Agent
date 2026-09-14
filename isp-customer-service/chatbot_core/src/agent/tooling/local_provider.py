"""
LocalToolProvider — the in-process tool implementations (agent/tools.py)
behind the ToolProvider port.
"""

from __future__ import annotations

import json
from typing import Any

from src.ports.tools import ToolSpec

# Demo-world simulations (the caller's physical actions on the seeded line),
# not offered to the LLM. Callers guard them with the SIMULATE_* flags.
DEMO_TOOLS = ("simulate_router_reboot", "simulate_bridge_connect", "simulate_bridge_disconnect")


class LocalToolProvider:
    """Runs the tools as local Python functions against the demo database."""

    def available_tools(self) -> list[ToolSpec]:
        from ..tools import REAL_TOOLS

        return [ToolSpec(t.name, t.description, t.parameters) for t in REAL_TOOLS]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        from .. import tools

        if tool_name in DEMO_TOOLS:
            result = getattr(tools, tool_name)(arguments["customer_id"])
            return json.dumps(result, ensure_ascii=False)
        return tools.execute_tool(tool_name, arguments)
