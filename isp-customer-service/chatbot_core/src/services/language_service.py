"""
Language Service - Multi-language support for ISP Customer Service Agent

Simple translation service that loads messages from YAML files.

Usage:
    from src.services.language_service import t, set_language, get_language
    
    # Set language
    set_language("lt")
    
    # Get translation
    greeting = t("greeting", company_name="SUN CITY")
    # -> "Labas! Čia SUN CITY klientų aptarnavimas. Kuo galiu padėti?"
    
    # Nested keys
    goodbye = t("cli.goodbye")
    # -> "Pokalbis baigtas. Viso gero!"
"""

import logging
from pathlib import Path
from typing import Any
from functools import lru_cache

import yaml

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

SUPPORTED_LANGUAGES = ["lt", "en"]
DEFAULT_LANGUAGE = "lt"

# Path to i18n folder (relative to this file)
# src/services/language_service.py -> src/config/i18n/
I18N_DIR = Path(__file__).parent.parent / "config" / "i18n"

# =============================================================================
# LANGUAGE STATE
# =============================================================================

_current_language: str = DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """
    Set current language.
    
    Args:
        lang: Language code ("lt" or "en")
    """
    global _current_language
    
    if lang not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language '{lang}', using '{DEFAULT_LANGUAGE}'")
        lang = DEFAULT_LANGUAGE
    
    _current_language = lang
    logger.debug(f"Language set to: {lang}")


def get_language() -> str:
    """Get current language code."""
    return _current_language


def get_language_name() -> str:
    """
    Get language name for LLM prompts.
    
    Returns:
        "Lithuanian" or "English"
    """
    names = {
        "lt": "Lithuanian",
        "en": "English",
    }
    return names.get(_current_language, "English")


# =============================================================================
# TRANSLATION LOADING
# =============================================================================

@lru_cache(maxsize=4)
def _load_messages(lang: str) -> dict:
    """
    Load messages from YAML file.
    
    Args:
        lang: Language code
        
    Returns:
        Messages dictionary
    """
    yaml_path = I18N_DIR / lang / "messages.yaml"
    
    if not yaml_path.exists():
        logger.error(f"Messages file not found: {yaml_path}")
        # Fallback to default language
        if lang != DEFAULT_LANGUAGE:
            return _load_messages(DEFAULT_LANGUAGE)
        return {}
    
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            messages = yaml.safe_load(f)
        logger.debug(f"Loaded messages for '{lang}': {len(messages)} keys")
        return messages or {}
    except Exception as e:
        logger.error(f"Error loading messages for '{lang}': {e}")
        return {}


def reload_messages() -> None:
    """Clear cache and reload messages."""
    _load_messages.cache_clear()
    logger.info("Messages cache cleared")


# =============================================================================
# TRANSLATION FUNCTION
# =============================================================================

def t(key: str, **kwargs) -> str:
    """
    Get translated message.
    
    Args:
        key: Message key (supports nested keys like "cli.goodbye")
        **kwargs: Format arguments (e.g., company_name="SUN CITY")
        
    Returns:
        Translated and formatted message
        
    Examples:
        t("greeting", company_name="SUN CITY")
        t("cli.goodbye")
        t("error")
    """
    messages = _load_messages(_current_language)
    
    # Handle nested keys (e.g., "cli.goodbye")
    value = messages
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break
    
    # Key not found
    if value is None:
        logger.warning(f"Translation not found: '{key}' [{_current_language}]")
        return f"[{key}]"
    
    # Not a string (nested dict without final key)
    if not isinstance(value, str):
        logger.warning(f"Translation key '{key}' is not a string")
        return f"[{key}]"
    
    # Format with kwargs
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format key {e} in translation '{key}'")
            return value
    
    return value


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_available_languages() -> list[dict]:
    """
    Get list of available languages.
    
    Returns:
        List of language info dicts
    """
    return [
        {"code": "lt", "name": "Lietuvių", "flag": "🇱🇹"},
        {"code": "en", "name": "English", "flag": "🇬🇧"},
    ]


def is_valid_language(lang: str) -> bool:
    """Check if language code is valid."""
    return lang in SUPPORTED_LANGUAGES


def get_output_language_instruction() -> str:
    """
    Get instruction for LLM to respond in correct language.
    
    Returns:
        Instruction string for system prompt
    """
    lang_name = get_language_name()
    
    if _current_language == "lt":
        return f"CRITICAL: Respond ONLY in {lang_name}. Use INFORMAL 'tu' form (not 'Jūs')."
    else:
        return f"CRITICAL: Respond ONLY in {lang_name}."


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("Testing Language Service\n")
    
    # Test LT
    print("=== Lithuanian ===")
    set_language("lt")
    print(f"Language: {get_language()} ({get_language_name()})")
    print(f"Greeting: {t('greeting', company_name='SUN CITY')}")
    print(f"Error: {t('error')}")
    print(f"CLI goodbye: {t('cli.goodbye')}")
    print(f"LLM instruction: {get_output_language_instruction()}")
    
    print("\n=== English ===")
    set_language("en")
    print(f"Language: {get_language()} ({get_language_name()})")
    print(f"Greeting: {t('greeting', company_name='SUN CITY')}")
    print(f"Error: {t('error')}")
    print(f"CLI goodbye: {t('cli.goodbye')}")
    print(f"LLM instruction: {get_output_language_instruction()}")
    
    print("\n=== Missing key ===")
    print(f"Missing: {t('nonexistent.key')}")
