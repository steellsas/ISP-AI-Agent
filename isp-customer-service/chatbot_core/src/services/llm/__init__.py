"""
LLM Service Package

Multi-provider LLM support with token tracking, caching, and rate limiting.

Usage:
    from services.llm import llm_completion, llm_json_completion

    # Simple completion
    response = llm_completion(messages=[{"role": "user", "content": "Hello"}])

    # JSON completion
    data = llm_json_completion(messages=[...])

    # Change settings
    update_settings(model="gpt-4o", temperature=0.5)

    # Get stats
    stats = get_session_stats().to_dict()
"""

# Main completion functions
from .client import (
    llm_completion,
    llm_json_completion,
    quick_completion,
    quick_json,
)

# Models
from .models import (
    ModelInfo,
    MODEL_REGISTRY,
    get_available_models,
    get_models_by_provider,
    get_model_info,
    calculate_cost,
    estimate_cost,
)

# Settings
from .settings import (
    LLMSettings,
    get_settings,
    update_settings,
    reset_settings,
    set_model,
    set_temperature,
    set_max_tokens,
)

# Statistics
from .stats import (
    CallStats,
    SessionStats,
    get_session_stats,
    reset_session_stats,
    record_call,
)

# Rate limiting
from .rate_limiter import (
    RateLimiter,
    RateLimitError,
    get_rate_limiter,
    reset_rate_limiter,
)

# Caching
from .cache import (
    ResponseCache,
    get_cache,
    clear_cache,
)

# Utilities
from .utils import (
    get_api_key,
    check_api_keys,
    get_available_providers,
    extract_json_from_response,
    validate_json_response,
    LLMError,
)


# =============================================================================
# Convenience Functions
# =============================================================================


def get_full_status() -> dict:
    """Get complete status for UI display."""
    return {
        "settings": get_settings().to_dict(),
        "stats": get_session_stats().to_dict(),
        "rate_limit": get_rate_limiter().get_status(),
        "cache": get_cache().get_stats(),
        "available_providers": get_available_providers(),
        "available_models": get_available_models(),
    }


def get_usage_summary() -> str:
    """Get human-readable usage summary."""
    return get_session_stats().get_summary_text()


def initialize(
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> dict:
    """
    Initialize LLM service with optional settings.

    Returns:
        Dict with available providers info
    """
    if model:
        update_settings(model=model)
    if temperature is not None:
        update_settings(temperature=temperature)
    if max_tokens:
        update_settings(max_tokens=max_tokens)

    providers = get_available_providers()

    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"LLM Service initialized. Providers: {providers}")

    return {
        "available_providers": providers,
        "api_keys": check_api_keys(),
        "current_model": get_settings().model,
    }


# =============================================================================
# Backwards Compatibility
# =============================================================================


def get_openai_api_key() -> str:
    """Get OpenAI API key (backwards compatibility)."""
    return get_api_key("openai")


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Main functions
    "llm_completion",
    "llm_json_completion",
    "quick_completion",
    "quick_json",
    # Models
    "ModelInfo",
    "MODEL_REGISTRY",
    "get_available_models",
    "get_models_by_provider",
    "get_model_info",
    "calculate_cost",
    "estimate_cost",
    # Settings
    "LLMSettings",
    "get_settings",
    "update_settings",
    "reset_settings",
    "set_model",
    "set_temperature",
    "set_max_tokens",
    # Statistics
    "CallStats",
    "SessionStats",
    "get_session_stats",
    "reset_session_stats",
    # Rate limiting
    "RateLimiter",
    "RateLimitError",
    "get_rate_limiter",
    # Caching
    "ResponseCache",
    "get_cache",
    "clear_cache",
    # Utilities
    "get_api_key",
    "check_api_keys",
    "get_available_providers",
    "LLMError",
    # Convenience
    "get_full_status",
    "get_usage_summary",
    "initialize",
    # Backwards compatibility
    "get_openai_api_key",
]
