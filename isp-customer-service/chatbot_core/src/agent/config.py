"""
Agent Configuration

Single configuration source for the entire ISP Support Agent.
Used by: ReactAgent, LLM services, Streamlit UI

Usage:
    from src.agent.config import get_config, create_config, update_config
    
    # Get default config
    config = get_config()
    
    # Create config with custom settings
    config = create_config(language="en", model="gpt-4o")
    
    # Update runtime settings
    update_config(temperature=0.5)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """
    Complete configuration for ISP Support Agent.
    
    Includes: company info, language, agent behavior, LLM settings.
    """
    
    # =========================================================================
    # Company & Identity
    # =========================================================================
    company_name: str = "SUN CITY"
    
    # =========================================================================
    # Language Settings
    # =========================================================================
    language: str = "lt"  # "lt" or "en"
    formal: bool = False  # True = "Jūs", False = "tu" (only for LT)
    
    # =========================================================================
    # Agent Behavior
    # =========================================================================
    max_turns: int = 20
    max_tool_calls_per_response: int = 5
    debug_mode: bool = False
    
    # =========================================================================
    # LLM Model Settings
    # =========================================================================
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 500
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    
    # =========================================================================
    # LLM Retry Settings
    # =========================================================================
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # =========================================================================
    # LLM Cache Settings
    # =========================================================================
    enable_cache: bool = True
    cache_ttl_seconds: int = 300
    
    # =========================================================================
    # LLM Rate Limiting
    # =========================================================================
    max_calls_per_minute: int = 30
    max_calls_per_session: int = 100
    
    # =========================================================================
    # Post Init - Set language service
    # =========================================================================
    
    def __post_init__(self):
        """Initialize language service with configured language."""
        from src.services.language_service import set_language
        set_language(self.language)
    
    # =========================================================================
    # Message Properties (from language service)
    # =========================================================================
    
    @property
    def greeting_message(self) -> str:
        """Get greeting message in current language."""
        from src.services.language_service import t
        return t("greeting", company_name=self.company_name)
    
    @property
    def error_message(self) -> str:
        """Get error message in current language."""
        from src.services.language_service import t
        return t("error")
    
    @property
    def timeout_message(self) -> str:
        """Get timeout message in current language."""
        from src.services.language_service import t
        return t("timeout")
    
    @property
    def max_turns_message(self) -> str:
        """Get max turns message in current language."""
        from src.services.language_service import t
        return t("max_turns")
    
    @property
    def conversation_end_message(self) -> str:
        """Get conversation end message in current language."""
        from src.services.language_service import t
        return t("conversation_ended")
    
    @property
    def cli_goodbye_message(self) -> str:
        """Get CLI goodbye message in current language."""
        from src.services.language_service import t
        return t("cli.goodbye")
    
    @property
    def cli_interrupted_message(self) -> str:
        """Get CLI interrupted message in current language."""
        from src.services.language_service import t
        return t("cli.interrupted")


# =============================================================================
# Global Config Instance
# =============================================================================

_default_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """
    Get current configuration.
    
    Creates default config on first call.
    """
    global _default_config
    if _default_config is None:
        _default_config = AgentConfig()
    return _default_config


def create_config(**kwargs) -> AgentConfig:
    """
    Create new configuration with custom settings.
    
    Args:
        **kwargs: Any AgentConfig field
        
    Returns:
        New AgentConfig instance
        
    Example:
        config = create_config(language="en", model="gpt-4o", temperature=0.5)
    """
    return AgentConfig(**kwargs)


def update_config(**kwargs) -> AgentConfig:
    """
    Update default configuration.
    
    Args:
        **kwargs: Fields to update
        
    Returns:
        Updated config
    """
    global _default_config
    config = get_config()
    
    # Update language service if language changed
    if "language" in kwargs:
        from src.services.language_service import set_language
        set_language(kwargs["language"])
    
    # Update fields
    for key, value in kwargs.items():
        if hasattr(config, key):
            object.__setattr__(config, key, value)
    
    return config


def reset_config() -> AgentConfig:
    """Reset to default configuration."""
    global _default_config
    _default_config = AgentConfig()
    return _default_config


# =============================================================================
# Convenience Functions
# =============================================================================

def set_model(model_id: str) -> None:
    """Change LLM model."""
    update_config(model=model_id)


def set_language(lang: str) -> None:
    """Change language."""
    update_config(language=lang)


def set_temperature(temp: float) -> None:
    """Change temperature."""
    if 0 <= temp <= 2:
        update_config(temperature=temp)
    else:
        raise ValueError("Temperature must be between 0 and 2")
