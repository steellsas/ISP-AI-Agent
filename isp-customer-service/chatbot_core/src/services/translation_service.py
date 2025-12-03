"""
Translation Service - Loads and provides translated messages.

Uses YAML files per language:
- i18n/lt/messages.yaml
- i18n/en/messages.yaml

Usage:
    from src.services.translation_service import t
    
    message = t("greeting.welcome")
    message = t("address.confirm", customer_name="Jonas", address="Vilnius, Gedimino 1")
"""

import logging
from pathlib import Path
from typing import Any
from functools import lru_cache
import yaml

from .language_service import get_language, SupportedLanguage

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Path to i18n directory (relative to this file)
# Adjust if your project structure is different
I18N_DIR = Path(__file__).parent.parent / "config" / "i18n"

# Fallback language if translation not found
FALLBACK_LANGUAGE: SupportedLanguage = "lt"

# Cache for loaded translations
_translations_cache: dict[str, dict] = {}


# =============================================================================
# YAML LOADING
# =============================================================================

def _find_i18n_dir() -> Path:
    """
    Find i18n directory. Tries multiple locations.
    
    Returns:
        Path to i18n directory
    """
    # Try relative to this file
    candidates = [
        Path(__file__).parent.parent / "config" / "i18n",
        Path(__file__).parent.parent.parent / "config" / "i18n",
        Path(__file__).parent.parent / "i18n",
        Path("src/config/i18n"),
        Path("config/i18n"),
        Path("i18n"),
    ]
    
    for path in candidates:
        if path.exists():
            return path
    
    # Return default (will be created if needed)
    return candidates[0]


def _load_yaml_file(file_path: Path) -> dict:
    """Load single YAML file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except FileNotFoundError:
        logger.warning(f"Translation file not found: {file_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"YAML parse error in {file_path}: {e}")
        return {}


def _load_language_translations(language: SupportedLanguage) -> dict:
    """
    Load all translation files for a language.
    
    Loads:
    - messages.yaml (main messages)
    - phrases.yaml (yes/no, help phrases) - optional
    - errors.yaml (error messages) - optional
    
    Args:
        language: Language code ('lt' or 'en')
        
    Returns:
        Merged translations dict
    """
    i18n_dir = _find_i18n_dir()
    lang_dir = i18n_dir / language
    
    if not lang_dir.exists():
        logger.warning(f"Language directory not found: {lang_dir}")
        return {}
    
    translations = {}
    
    # Load all YAML files in language directory
    yaml_files = ["messages.yaml", "phrases.yaml", "errors.yaml"]
    
    for filename in yaml_files:
        file_path = lang_dir / filename
        if file_path.exists():
            data = _load_yaml_file(file_path)
            translations.update(data)
            logger.debug(f"Loaded {file_path}: {len(data)} keys")
    
    return translations


def get_translations(language: SupportedLanguage | None = None) -> dict:
    """
    Get translations for language (with caching).
    
    Args:
        language: Language code, or None for current language
        
    Returns:
        Translations dict
    """
    if language is None:
        language = get_language()
    
    if language not in _translations_cache:
        _translations_cache[language] = _load_language_translations(language)
        logger.info(f"Loaded {len(_translations_cache[language])} translation keys for '{language}'")
    
    return _translations_cache[language]


def reload_translations() -> None:
    """Clear cache and reload all translations."""
    global _translations_cache
    _translations_cache = {}
    logger.info("Translation cache cleared")


# =============================================================================
# TRANSLATION FUNCTION
# =============================================================================

def _get_nested_value(data: dict, key_path: str, default: Any = None) -> Any:
    """
    Get value from nested dict using dot notation.
    
    Args:
        data: Nested dictionary
        key_path: Dot-separated path like "greeting.welcome"
        default: Default value if not found
        
    Returns:
        Value at path or default
    """
    keys = key_path.split(".")
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def t(
    key: str,
    default: str | None = None,
    language: SupportedLanguage | None = None,
    **kwargs
) -> str:
    """
    Get translated message.
    
    This is the main translation function. Use it everywhere!
    
    Args:
        key: Translation key using dot notation (e.g., "greeting.welcome")
        default: Default value if translation not found
        language: Override language (usually not needed)
        **kwargs: Format parameters for the message
        
    Returns:
        Translated and formatted message
        
    Examples:
        t("greeting.welcome")
        t("address.confirm", customer_name="Jonas", address="Vilnius")
        t("errors.not_found", default="Not found")
        t("greeting.welcome", language="en")  # Force English
    """
    # Get translations for language
    if language is None:
        language = get_language()
    
    translations = get_translations(language)
    
    # Try to get translation
    message = _get_nested_value(translations, key)
    
    # Fallback to other language
    if message is None and language != FALLBACK_LANGUAGE:
        fallback_translations = get_translations(FALLBACK_LANGUAGE)
        message = _get_nested_value(fallback_translations, key)
        if message is not None:
            logger.debug(f"Using fallback translation for '{key}'")
    
    # Use default or key itself
    if message is None:
        if default is not None:
            message = default
        else:
            logger.warning(f"Translation not found: '{key}'")
            message = f"[{key}]"  # Return key for debugging
    
    # Format with parameters
    if kwargs and isinstance(message, str):
        try:
            message = message.format(**kwargs)
        except KeyError as e:
            logger.error(f"Missing format parameter for '{key}': {e}")
        except Exception as e:
            logger.error(f"Format error for '{key}': {e}")
    
    return message


def t_list(key: str, language: SupportedLanguage | None = None) -> list[str]:
    """
    Get translation as list.
    
    Useful for phrases lists (yes_phrases, no_phrases, etc.)
    
    Args:
        key: Translation key
        language: Override language
        
    Returns:
        List of strings, or empty list if not found
    """
    if language is None:
        language = get_language()
    
    translations = get_translations(language)
    value = _get_nested_value(translations, key)
    
    if isinstance(value, list):
        return value
    elif value is None:
        return []
    else:
        return [str(value)]


def t_dict(key: str, language: SupportedLanguage | None = None) -> dict:
    """
    Get translation as dict.
    
    Useful for nested message groups.
    
    Args:
        key: Translation key
        language: Override language
        
    Returns:
        Dict or empty dict if not found
    """
    if language is None:
        language = get_language()
    
    translations = get_translations(language)
    value = _get_nested_value(translations, key)
    
    if isinstance(value, dict):
        return value
    else:
        return {}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def has_translation(key: str, language: SupportedLanguage | None = None) -> bool:
    """Check if translation exists for key."""
    if language is None:
        language = get_language()
    
    translations = get_translations(language)
    return _get_nested_value(translations, key) is not None


def get_all_keys(language: SupportedLanguage | None = None) -> list[str]:
    """
    Get all translation keys (for debugging).
    
    Returns:
        List of all available translation keys
    """
    def _flatten_keys(data: dict, prefix: str = "") -> list[str]:
        keys = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys.extend(_flatten_keys(value, full_key))
            else:
                keys.append(full_key)
        return keys
    
    translations = get_translations(language)
    return _flatten_keys(translations)


# =============================================================================
# INITIALIZATION CHECK
# =============================================================================

def ensure_i18n_structure() -> Path:
    """
    Ensure i18n directory structure exists.
    
    Creates directories if needed. Returns path to i18n dir.
    """
    i18n_dir = _find_i18n_dir()
    
    # Create structure
    for lang in ["lt", "en"]:
        lang_dir = i18n_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        
        # Create empty messages.yaml if not exists
        messages_file = lang_dir / "messages.yaml"
        if not messages_file.exists():
            messages_file.write_text("# Messages for " + lang + "\n", encoding="utf-8")
            logger.info(f"Created {messages_file}")
    
    return i18n_dir


# =============================================================================
# TESTING / DEBUG
# =============================================================================

if __name__ == "__main__":
    from .language_service import set_language
    
    print("=== Translation Service Test ===")
    
    # Ensure structure exists
    i18n_dir = ensure_i18n_structure()
    print(f"\ni18n directory: {i18n_dir}")
    
    # Test with Lithuanian
    set_language("lt")
    print(f"\n--- Lithuanian ---")
    print(f"greeting.welcome: {t('greeting.welcome', default='Labas!')}")
    print(f"Has 'greeting.welcome': {has_translation('greeting.welcome')}")
    
    # Test with parameters
    print(f"\nWith params: {t('address.confirm', default='Adresas: {address}', address='Vilnius')}")
    
    # Test English
    set_language("en")
    print(f"\n--- English ---")
    print(f"greeting.welcome: {t('greeting.welcome', default='Hello!')}")
    
    # List all keys
    print(f"\n--- All keys ---")
    for key in get_all_keys()[:10]:  # First 10
        print(f"  {key}")