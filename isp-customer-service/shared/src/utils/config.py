"""
Configuration Management
Environment variables and settings loader
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


def load_env(env_file: Optional[Path] = None) -> bool:
    """
    Load environment variables from .env file.
    
    Args:
        env_file: Path to .env file (defaults to project root/.env)
    
    Returns:
        True if .env file was loaded, False otherwise
    """
    if env_file is None:
        # Try to find .env in project root
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels up
            env_path = current / ".env"
            if env_path.exists():
                env_file = env_path
                break
            current = current.parent
    
    if env_file and env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment from: {env_file}")
        return True
    else:
        logger.warning("No .env file found")
        return False


class Config:
    """
    Configuration container with environment variable access.
    """
    
    def __init__(self) -> None:
        """Initialize configuration from environment."""
        # Database
        self.database_path = os.getenv(
            "DATABASE_PATH",
            "database/isp_database.db"
        )
        
        # OpenAI API
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4")
        
        # LangSmith (optional)
        self.langsmith_api_key = os.getenv("LANGCHAIN_API_KEY", "")
        self.langsmith_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        self.langsmith_project = os.getenv("LANGCHAIN_PROJECT", "isp-customer-service")
        
        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Service ports (for MCP servers)
        self.crm_service_port = int(os.getenv("CRM_SERVICE_PORT", "8001"))
        self.network_service_port = int(os.getenv("NETWORK_SERVICE_PORT", "8002"))
        
        # UI
        self.streamlit_port = int(os.getenv("STREAMLIT_PORT", "8501"))
        
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
        
        Returns:
            Configuration value or default
        """
        return getattr(self, key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary of configuration values
        """
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
    
    def validate(self) -> bool:
        """
        Validate required configuration.
        
        Returns:
            True if valid, False otherwise
        """
        errors = []
        
        # Check database path
        db_path = Path(self.database_path)
        if not db_path.exists():
            errors.append(f"Database not found: {db_path}")
        
        # Check OpenAI API key
        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY not set")
        
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            return False
        
        return True


# Global configuration instance
_config: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """
    Get global configuration instance.
    
    Args:
        reload: Force reload configuration from environment
    
    Returns:
        Config instance
    """
    global _config
    
    if _config is None or reload:
        load_env()
        _config = Config()
    
    return _config