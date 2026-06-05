"""
Configuration Management
Environment variables and settings loader
"""

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_env(env_file: Path | None = None) -> bool:
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
        self.database_path = os.getenv("DATABASE_PATH", "database/isp_database.db")

        # OpenAI API
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        # LangSmith (optional)
        self.langsmith_api_key = os.getenv("LANGCHAIN_API_KEY", "")
        self.langsmith_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        self.langsmith_project = os.getenv("LANGCHAIN_PROJECT", "isp-customer-service")
        self.langsmith_endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        # PII redaction: phone numbers are masked in logs by default. Set
        # REDACT_PII=false locally to keep full numbers for test traceability;
        # deployed environments should leave it on.
        self.redact_pii = os.getenv("REDACT_PII", "true").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )

        # Service ports (for MCP servers)
        self.crm_service_port = int(os.getenv("CRM_SERVICE_PORT", "8001"))
        self.network_service_port = int(os.getenv("NETWORK_SERVICE_PORT", "8002"))

        # UI
        self.streamlit_port = int(os.getenv("STREAMLIT_PORT", "8501"))

        # RAG / retrieval — single source for tuning knobs that were previously
        # scattered across call sites (tools.py, retriever/hybrid defaults). The
        # embedding dimension is intentionally NOT here: it must come from the
        # model so swapping models can't silently mismatch the index.
        self.rag_model_name = os.getenv(
            "RAG_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        )
        # "flatip" (true cosine, with L2-normalized vectors) vs "flatl2"
        # (Euclidean, mapped to a similarity via 1/(1+dist)). flatip makes the
        # score a directly interpretable cosine in [-1, 1], so the threshold
        # below is a real relevance floor — the payoff grows as the KB grows.
        self.rag_index_type = os.getenv("RAG_INDEX_TYPE", "flatip")
        self.rag_top_k = int(os.getenv("RAG_TOP_K", "3"))
        self.rag_threshold = float(os.getenv("RAG_THRESHOLD", "0.4"))
        self.rag_keyword_weight = float(os.getenv("RAG_KEYWORD_WEIGHT", "0.3"))
        # Default language stamped on KB chunks that don't live under a
        # language folder (knowledge_base/<lang>/...). Makes language a data
        # dimension: today everything is "lt"; adding an "en/" folder later is
        # picked up automatically, so retrieval can filter to the caller's
        # language (filter_metadata={"lang": ...}) with zero code change.
        self.rag_default_lang = os.getenv("RAG_DEFAULT_LANG", "lt")

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

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary of configuration values
        """
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}

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

    def apply_to_environment(self) -> None:
        """
        Apply configuration to os.environ for LangSmith auto-detection.

        LangSmith automatically reads from os.environ, so we set them here.
        """
        # Set LangSmith env vars
        if self.langsmith_tracing:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"

        if self.langsmith_api_key:
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key

        if self.langsmith_project:
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project

        if self.langsmith_endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_endpoint

    def print_status(self, verbose: bool = False) -> None:
        """
        Print configuration status.

        Args:
            verbose: Show detailed configuration
        """
        print("\n" + "=" * 60)
        print("📋 CONFIGURATION STATUS")
        print("=" * 60)

        # OpenAI
        if self.openai_api_key:
            key_preview = (
                self.openai_api_key[:12] + "..." if len(self.openai_api_key) > 12 else "***"
            )
            print(f"✅ OpenAI API Key: {key_preview}")
            print(f"   Model: {self.openai_model}")
        else:
            print("❌ OpenAI API Key: Not set")

        # LangSmith
        print(
            f"\n{'✅' if self.langsmith_tracing else '⚠️ '} LangSmith Tracing: {self.langsmith_tracing}"
        )
        if self.langsmith_api_key:
            key_preview = (
                self.langsmith_api_key[:12] + "..." if len(self.langsmith_api_key) > 12 else "***"
            )
            print(f"✅ LangSmith API Key: {key_preview}")
            print(f"   Project: {self.langsmith_project}")
            print(f"   Endpoint: {self.langsmith_endpoint}")
        else:
            if self.langsmith_tracing:
                print("⚠️  LangSmith API Key: Not set (tracing enabled but no key)")
            else:
                print("ℹ️  LangSmith API Key: Not set (tracing disabled)")

        # Database
        db_path = Path(self.database_path)
        if db_path.exists():
            print(f"\n✅ Database: {self.database_path}")
        else:
            print(f"\n❌ Database: {self.database_path} (not found)")

        # Verbose details
        if verbose:
            print("\n📊 Full Configuration:")
            for key, value in self.to_dict().items():
                # Mask sensitive data
                if "key" in key.lower() or "api" in key.lower():
                    if value and len(str(value)) > 12:
                        display_value = str(value)[:12] + "..."
                    else:
                        display_value = "***" if value else "Not set"
                else:
                    display_value = value
                print(f"   {key}: {display_value}")

        print("=" * 60 + "\n")


# Global configuration instance
_config: Config | None = None


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
        _config.apply_to_environment()  # Apply to os.environ for LangSmith

    return _config
