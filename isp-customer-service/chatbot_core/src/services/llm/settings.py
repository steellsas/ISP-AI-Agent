"""
LLM Settings

Bridge between AgentConfig and LLM client.
Gets settings from centralized AgentConfig.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMSettings:
    """LLM settings for client.py"""
    
    # Model settings
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 500
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    
    # Rate limiting
    max_calls_per_minute: int = 30
    max_calls_per_session: int = 100
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Caching
    enable_cache: bool = True
    cache_ttl_seconds: int = 300
    
    def to_dict(self) -> dict:
        """Convert to dictionary for UI/serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "LLMSettings":
        """Create from dictionary."""
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def _load_from_agent_config() -> LLMSettings:
    """Load LLM settings from AgentConfig."""
    try:
        from src.agent.config import get_config
        config = get_config()
        
        settings = LLMSettings(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
            max_calls_per_minute=config.max_calls_per_minute,
            max_calls_per_session=config.max_calls_per_session,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            enable_cache=config.enable_cache,
            cache_ttl_seconds=config.cache_ttl_seconds,
        )
        
        logger.debug(f"Loaded LLM settings from AgentConfig: model={settings.model}")
        return settings
        
    except ImportError as e:
        logger.warning(f"Could not import AgentConfig: {e}, using defaults")
        return LLMSettings()
    except Exception as e:
        logger.warning(f"Error loading from AgentConfig: {e}, using defaults")
        return LLMSettings()


# =============================================================================
# Global Settings Instance
# =============================================================================

_current_settings: Optional[LLMSettings] = None


def get_settings() -> LLMSettings:
    """Get current LLM settings (loads from AgentConfig on first call)."""
    global _current_settings
    if _current_settings is None:
        _current_settings = _load_from_agent_config()
    return _current_settings


def refresh_settings() -> LLMSettings:
    """Refresh settings from AgentConfig (call after config changes)."""
    global _current_settings
    _current_settings = _load_from_agent_config()
    return _current_settings


def update_settings(**kwargs) -> LLMSettings:
    """
    Update LLM settings.
    
    Note: This updates local settings AND AgentConfig.
    """
    global _current_settings
    settings = get_settings()
    
    # Update AgentConfig too
    try:
        from src.agent.config import update_config
        update_config(**kwargs)
    except ImportError:
        pass
    
    # Update local settings
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
            logger.debug(f"Updated setting: {key} = {value}")
        else:
            logger.warning(f"Unknown setting: {key}")
    
    return settings


def reset_settings() -> LLMSettings:
    """Reset settings from AgentConfig."""
    global _current_settings
    _current_settings = _load_from_agent_config()
    logger.info("Settings refreshed from AgentConfig")
    return _current_settings


# =============================================================================
# Convenience Functions
# =============================================================================

def set_model(model_id: str) -> None:
    """Change model."""
    update_settings(model=model_id)


def set_temperature(temp: float) -> None:
    """Change temperature."""
    if 0 <= temp <= 2:
        update_settings(temperature=temp)
    else:
        raise ValueError("Temperature must be between 0 and 2")


def set_max_tokens(tokens: int) -> None:
    """Change max tokens."""
    if tokens > 0:
        update_settings(max_tokens=tokens)
    else:
        raise ValueError("Max tokens must be positive")
