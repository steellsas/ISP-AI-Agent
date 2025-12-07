"""
ISP Customer Support Agent

ReAct (Reasoning + Acting) pattern implementation for customer support.

Usage:
    from agent import ReactAgent
    
    agent = ReactAgent(caller_phone="+37060012345")
    
    # Get initial greeting
    response = agent.run_until_response()
    print(response)  # "Labas! Kuo galiu padėti?"
    
    # Process customer message
    response = agent.run_until_response("Neveikia internetas")
    print(response)
    
CLI Usage:
    python -m src.agent.react_agent
"""

from .react_agent import ReactAgent, run_cli
from .state import AgentState
from .config import AgentConfig, get_config, update_config
from .tools import REAL_TOOLS, execute_tool, get_tools_description

# Backwards compatibility
run_agent = run_cli

__all__ = [
    # Main class
    "ReactAgent",
    
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
    
    # CLI
    "run_cli",
    "run_agent",  # backwards compat
]
