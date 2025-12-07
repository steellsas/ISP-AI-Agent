"""
LLM Service Package

Simplified LLM support for ReactAgent.

Usage:
    from services.llm import llm_completion

    # Simple completion
    response = llm_completion(messages=[{"role": "user", "content": "Hello"}])

    # JSON completion  
    data = llm_json_completion(messages=[...])
"""

# Main completion functions
from .client import (
    llm_completion,
    llm_json_completion,
    get_last_call_stats,
    get_model_info,
    extract_json_from_response,
    validate_json_response,
)

# Settings
from .settings import (
    LLMSettings,
    get_settings,
    update_settings,
    refresh_settings,
    reset_settings,
    set_model,
    set_temperature,
    set_max_tokens,
)


__all__ = [
    # Main functions
    "llm_completion",
    "llm_json_completion",
    "get_last_call_stats",
    "get_model_info",
    "extract_json_from_response",
    "validate_json_response",
    # Settings
    "LLMSettings",
    "get_settings",
    "update_settings",
    "refresh_settings",
    "reset_settings",
    "set_model",
    "set_temperature",
    "set_max_tokens",
]