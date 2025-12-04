"""
Configuration loader for ISP Support Agent
"""

from pathlib import Path
import yaml
from pydantic import BaseModel
from functools import lru_cache


class AgentConfig(BaseModel):
    """Agent identity configuration."""

    company_name: str
    agent_name: str
    language: str = "lt"


class GreetingConfig(BaseModel):
    """Greeting template configuration."""

    template: str


class ConversationConfig(BaseModel):
    """Conversation settings."""

    max_troubleshooting_attempts: int = 3
    timeout_seconds: int = 300


class LLMConfig(BaseModel):
    """LLM settings."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 500


class Config(BaseModel):
    """Main configuration."""

    agent: AgentConfig
    greeting: GreetingConfig
    conversation: ConversationConfig = ConversationConfig()
    llm: LLMConfig = LLMConfig()


def find_config_file() -> Path:
    """
    Find config.yaml file.

    Searches in:
    1. src/config/config.yaml (relative to cwd)
    2. config/config.yaml (relative to cwd)
    3. Same directory as this file
    """
    search_paths = [
        Path("src/config/config.yaml"),
        Path("config/config.yaml"),
        Path(__file__).parent / "config.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    raise FileNotFoundError(f"config.yaml not found. Searched: {[str(p) for p in search_paths]}")


@lru_cache(maxsize=1)
def load_config(config_path: str | None = None) -> Config:
    """
    Load config from YAML file.

    Uses lru_cache to load only once.

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Config object
    """
    if config_path:
        path = Path(config_path)
    else:
        path = find_config_file()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Config(**data)


def get_greeting(config: Config | None = None) -> str:
    """
    Generate greeting message from config.

    Args:
        config: Config object (loads if not provided)

    Returns:
        Formatted greeting string
    """
    if config is None:
        config = load_config()

    return config.greeting.template.format(
        company_name=config.agent.company_name, agent_name=config.agent.agent_name
    )


def reload_config() -> Config:
    """Force reload config (clears cache)."""
    load_config.cache_clear()
    return load_config()
