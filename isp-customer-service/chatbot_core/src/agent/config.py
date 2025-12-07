"""
Agent Configuration.

All configurable parameters for the ReAct agent.
Uses language_service for translated messages.
"""

from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Configuration for ReAct agent."""
    
    # LLM settings
    temperature: float = 0.3
    max_tokens: int = 1000
    
    # Agent limits
    max_turns: int = 20
    max_tool_calls_per_response: int = 5
    
    # Company info
    company_name: str = "SUN CITY"
    
    # Language ("lt" or "en")
    language: str = "lt"
    formal: bool = False  # True = "Jūs", False = "tu" (only for LT)
    
    # Debug
    debug_mode: bool = False
    
    def __post_init__(self):
        """Initialize language service with configured language."""
        from src.services.language_service import set_language
        set_language(self.language)
    
    # =========================================================================
    # Message properties - use language_service for translations
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


# Default configuration
DEFAULT_CONFIG = AgentConfig()


def get_config() -> AgentConfig:
    """Get agent configuration."""
    return DEFAULT_CONFIG


def create_config(language: str = "lt", **kwargs) -> AgentConfig:
    """
    Create new configuration with specified language.
    
    Args:
        language: Language code ("lt" or "en")
        **kwargs: Other config parameters
        
    Returns:
        New AgentConfig instance
    """
    return AgentConfig(language=language, **kwargs)


def update_config(**kwargs) -> AgentConfig:
    """Update default configuration with new values."""
    global DEFAULT_CONFIG
    
    # If language is being updated, re-initialize
    if "language" in kwargs:
        from src.services.language_service import set_language
        set_language(kwargs["language"])
    
    for key, value in kwargs.items():
        if hasattr(DEFAULT_CONFIG, key):
            object.__setattr__(DEFAULT_CONFIG, key, value)
    
    return DEFAULT_CONFIG
