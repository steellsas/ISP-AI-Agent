"""Shared utilities."""

from .logger import (
    # Core setup
    setup_logger,
    get_logger,
    setup_logging,
    # Service-specific
    setup_crm_logger,
    setup_network_logger,
    setup_chatbot_logger,
    setup_mcp_server_logger,
    # Convenience functions
    log_agent_action,
    log_tool_call,
    log_llm_call,
    log_error,
    # Filter class (if needed externally)
    SensitiveDataFilter,
)
from .config import get_config, load_env

__all__ = [
    # Core logger
    "setup_logger",
    "get_logger",
    "setup_logging",
    # Service-specific
    "setup_crm_logger",
    "setup_network_logger",
    "setup_chatbot_logger",
    "setup_mcp_server_logger",
    # Convenience
    "log_agent_action",
    "log_tool_call",
    "log_llm_call",
    "log_error",
    # Filter
    "SensitiveDataFilter",
    # Config
    "get_config",
    "load_env",
]