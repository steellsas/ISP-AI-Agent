"""
Localization package for multi-language support.
"""

from .loader import (
    t,
    get_language,
    set_language,
    get_available_languages,
)

__all__ = [
    "t",
    "get_language",
    "set_language",
    "get_available_languages",
]
