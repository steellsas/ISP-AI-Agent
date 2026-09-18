"""
ISP Customer Support Agent.

Usage:
    from agent import AgentSession

    session = AgentSession(caller_phone="+37060012345")
    print(session.greeting())
    print(session.handle_turn("Neveikia internetas"))
"""

from .config import AgentConfig, get_config, update_config
from .graph_v2 import GraphState
from .session import AgentSession
from .tools import REAL_TOOLS

__all__ = [
    # Stable conversation entry point
    "AgentSession",
    # State
    "GraphState",
    # Config
    "AgentConfig",
    "get_config",
    "update_config",
    # Tools
    "REAL_TOOLS",
]
