"""
Language loader for UI translations.
"""

import yaml
from pathlib import Path
from typing import Any

# Current language
_current_language = "lt"

# Cached translations
_translations: dict[str, dict] = {}

# Translations directory
_translations_dir = Path(__file__).parent / "translations"


def get_available_languages() -> list[dict]:
    """Get list of available languages."""
    return [
        {"code": "lt", "name": "Lietuvių", "flag": "🇱🇹"},
        {"code": "en", "name": "English", "flag": "🇬🇧"},
    ]


def get_language() -> str:
    """Get current language code."""
    return _current_language


def set_language(lang: str):
    """Set current language."""
    global _current_language
    available = [l["code"] for l in get_available_languages()]
    if lang in available:
        _current_language = lang
    else:
        raise ValueError(f"Language '{lang}' not available. Use one of: {available}")


def _load_translations(lang: str) -> dict:
    """Load translations for a language."""
    if lang in _translations:
        return _translations[lang]

    file_path = _translations_dir / f"{lang}.yaml"

    if not file_path.exists():
        print(f"Warning: Translation file not found: {file_path}")
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _translations[lang] = data
        return data
    except Exception as e:
        print(f"Error loading translations from {file_path}: {e}")
        return {}


def t(key: str, **kwargs) -> str:
    """
    Get translation by dot-notation key.

    Args:
        key: Dot-notation key, e.g. "call.phone_label"
        **kwargs: Format arguments, e.g. t("greeting", name="Jonas")

    Returns:
        Translated string or key if not found

    Example:
        t("call.call_button")  # Returns "📞 Skambinti" or "📞 Call"
    """
    translations = _load_translations(_current_language)

    # Navigate nested dict by dots
    value = translations
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            # Key not found - return key itself
            return key

    # Format with kwargs if provided
    if isinstance(value, str) and kwargs:
        try:
            return value.format(**kwargs)
        except KeyError:
            return value

    return value if isinstance(value, str) else key


def reload_translations():
    """Clear cache and reload translations."""
    global _translations
    _translations = {}
