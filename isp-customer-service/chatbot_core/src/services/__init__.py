"""
Services Package

Shared services for the ISP customer service chatbot.

Services:
- language_service: Language management (LT/EN) and translations
- llm: LLM completion calls
"""

# Language and Translation (all in one module now)
from .language_service import (
    # Language functions
    set_language,
    get_language,
    get_language_name,
    get_available_languages,
    is_valid_language,
    get_output_language_instruction,
    # Translation function
    t,
    reload_messages,
    # Constants
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
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