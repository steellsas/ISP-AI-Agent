"""
LocalToolProvider — the in-process tool implementations (agent/tools.py)
behind the ToolProvider port.
"""

from __future__ import annotations

from typing import Any

from src.ports.tools import ToolSpec


class LocalToolProvider:
    """Runs the tools as local Python functions against the demo database."""

    def available_tools(self) -> list[ToolSpec]:
        from ..tools import REAL_TOOLS

        return [ToolSpec(t.name, t.description, t.parameters) for t in REAL_TOOLS]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        from ..tools import execute_tool

        return execute_tool(tool_name, arguments)
