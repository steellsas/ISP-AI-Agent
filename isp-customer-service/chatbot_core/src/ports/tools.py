"""Tool port — catalog + executor for the agent's tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolSpec:
    """Provider-agnostic description of one callable tool.

    Mirrors the fields of ``agent/tools.Tool`` minus the bound Python function,
    so the core can advertise tools to the LLM without exposing implementation.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON-schema-style parameter map


@runtime_checkable
class ToolProvider(Protocol):
    """Catalog + executor for the tools the agent may call.

    Mirrors ``agent/tools.REAL_TOOLS`` + ``execute_tool``. Lets the core ask
    "what can I call?" and "run this" without knowing whether the tools are
    local Python functions, MCP servers, or remote HTTP APIs.
    """

    def available_tools(self) -> list[ToolSpec]:
        """List the tools this provider can execute."""
        ...

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Run ``tool_name`` with ``arguments``; return a JSON string result."""
        ...
