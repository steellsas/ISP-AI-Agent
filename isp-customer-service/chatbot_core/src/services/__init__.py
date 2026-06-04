"""
Services Package

Shared services for the ISP customer service chatbot.

Services:
- language_service: Language management (LT/EN) and translations
- llm: LLM completion calls
"""

# Language and Translation (all in one module now)
from .language_service import (
    # Constants
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_available_languages,
    get_language,
    get_language_name,
    get_output_language_instruction,
    is_valid_language,
    reload_messages,
    # Language functions
    set_language,
    # Translation function
    t,
)

# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Language Service
    "set_language",
    "get_language",
    "get_language_name",
    "get_available_languages",
    "is_valid_language",
    "get_output_language_instruction",
    # Translation
    "t",
    "reload_messages",
    # Constants
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
]
