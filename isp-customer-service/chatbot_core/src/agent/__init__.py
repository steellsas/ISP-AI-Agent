"""
ISP Customer Support Agent.

Usage:
    from agent import AgentSession

    session = AgentSession(caller_phone="+37060012345")
    print(session.greeting())
    print(session.handle_turn("Neveikia internetas"))
"""

from .config import AgentConfig, get_config, update_config
from .session import AgentSession
from .state import AgentState
from .tools import REAL_TOOLS, execute_tool, get_tools_description

__all__ = [
    # Stable conversation entry point
    "AgentSession",
    # State
    "AgentState",
    # Config
    "AgentConfig",
    "get_config",
    "update_config",
    # Tools
    "REAL_TOOLS",
    "execute_tool",
    "get_tools_description",
]
