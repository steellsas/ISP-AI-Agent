"""
LLM Settings

Configurable settings with config.yaml integration.
"""

import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LLMSettings:
    """LLM settings that can be adjusted via UI or config."""

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
        # Filter only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def load_settings_from_config() -> LLMSettings:
    """Load LLM settings from config.yaml."""
    config_paths = [
        Path(__file__).parent.parent / "config" / "config.yaml",
        Path(__file__).parent.parent.parent / "config" / "config.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)

                llm_config = config.get("llm", {})

                settings = LLMSettings(
                    model=llm_config.get("model", "gpt-4o-mini"),
                    temperature=llm_config.get("temperature", 0.3),
                    max_tokens=llm_config.get("max_tokens", 500),
                    top_p=llm_config.get("top_p", 1.0),
                    max_retries=llm_config.get("max_retries", 3),
                    enable_cache=llm_config.get("enable_cache", True),
                )

                logger.info(f"Loaded LLM settings from {config_path}")
                return settings

            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")

    logger.info("Using default LLM settings")
    return LLMSettings()


# =============================================================================
# Global Settings Instance
# =============================================================================

_current_settings: LLMSettings = None


def get_settings() -> LLMSettings:
    """Get current LLM settings (loads from config on first call)."""
    global _current_settings
    if _current_settings is None:
        _current_settings = load_settings_from_config()
    return _current_settings


def update_settings(**kwargs) -> LLMSettings:
    """Update LLM settings."""
    global _current_settings
    settings = get_settings()

    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
            logger.debug(f"Updated setting: {key} = {value}")
        else:
            logger.warning(f"Unknown setting: {key}")

    return settings


def reset_settings():
    """Reset settings to config.yaml defaults."""
    global _current_settings
    _current_settings = load_settings_from_config()
    logger.info("Settings reset to defaults")


def set_model(model_id: str):
    """Convenience function to change model."""
    update_settings(model=model_id)


def set_temperature(temp: float):
    """Convenience function to change temperature."""
    if 0 <= temp <= 2:
        update_settings(temperature=temp)
    else:
        raise ValueError("Temperature must be between 0 and 2")


def set_max_tokens(tokens: int):
    """Convenience function to change max tokens."""
    if tokens > 0:
        update_settings(max_tokens=tokens)
    else:
        raise ValueError("Max tokens must be positive")
