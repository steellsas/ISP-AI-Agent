"""
Language Service - Multi-language support for ISP Customer Service Chatbot

Handles:
- Language configuration and settings
- Per-conversation language tracking
- Synchronization with UI language settings
- Language name formatting for LLM prompts

Supported languages:
- lt: Lithuanian (default)
- en: English

Usage:
    # Sync from state (call at node start)
    sync_language_from_state(state)
    
    # Get current language
    lang = get_language()  # "lt" or "en"
    
    # Get language name for LLM prompts
    name = get_language_name()  # "Lithuanian" or "English"
    
    # Get agent name based on language
    agent = get_agent_name()  # "Andrius" or "Andrew"
"""

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

# =============================================================================
# TYPE DEFINITIONS (Backward compatibility)
# =============================================================================

SupportedLanguage = Literal["lt", "en"]  # Type alias for type hints

# =============================================================================
# LANGUAGE CONFIGURATION
# =============================================================================

LANGUAGE_CONFIG = {
    "lt": {
        "code": "lt",
        "name": "Lithuanian",
        "native_name": "Lietuvių",
        "default_agent_name": "Andrius",
        "flag": "🇱🇹",
    },
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "default_agent_name": "Andrew",
        "flag": "🇬🇧",
    },
}

DEFAULT_LANGUAGE = "lt"
FALLBACK_LANGUAGE = "lt"

# =============================================================================
# LANGUAGE STATE (Thread-safe singleton pattern)
# =============================================================================

class _LanguageState:
    """Singleton to hold current language state."""
    
    def __init__(self):
        self._global_language: str = DEFAULT_LANGUAGE
        self._conversation_languages: dict[str, str] = {}
    
    def set_language(self, lang: str, conversation_id: str | None = None) -> None:
        """Set language globally or per conversation."""
        if lang not in LANGUAGE_CONFIG:
            logger.warning(f"Invalid language '{lang}', using default '{DEFAULT_LANGUAGE}'")
            lang = DEFAULT_LANGUAGE
        
        if conversation_id:
            self._conversation_languages[conversation_id] = lang
            logger.debug(f"Set language for conversation {conversation_id}: {lang}")
        else:
            self._global_language = lang
            logger.debug(f"Set global language: {lang}")
    
    def get_language(self, conversation_id: str | None = None) -> str:
        """Get language for conversation or global default."""
        if conversation_id and conversation_id in self._conversation_languages:
            return self._conversation_languages[conversation_id]
        return self._global_language
    
    def clear_conversation(self, conversation_id: str) -> None:
        """Clear language setting for ended conversation."""
        if conversation_id in self._conversation_languages:
            del self._conversation_languages[conversation_id]
            logger.debug(f"Cleared language for conversation {conversation_id}")


# Global singleton instance
_language_state = _LanguageState()


# =============================================================================
# PUBLIC API - BASIC FUNCTIONS
# =============================================================================

def set_language(lang: str, conversation_id: str | None = None) -> None:
    """
    Set current language.
    
    Args:
        lang: Language code ("lt" or "en")
        conversation_id: Optional conversation ID for per-conversation language
    """
    _language_state.set_language(lang, conversation_id)


def get_language(conversation_id: str | None = None) -> str:
    """
    Get current language code.
    
    Args:
        conversation_id: Optional conversation ID
    
    Returns:
        Language code ("lt" or "en")
    """
    return _language_state.get_language(conversation_id)


def get_language_config(lang: str | None = None) -> dict:
    """
    Get full language configuration.
    
    Args:
        lang: Language code (uses current if None)
    
    Returns:
        Language config dict with code, name, native_name, agent_name, flag
    """
    if lang is None:
        lang = get_language()
    return LANGUAGE_CONFIG.get(lang, LANGUAGE_CONFIG[DEFAULT_LANGUAGE])


def get_language_name(conversation_id: str | None = None) -> str:
    """
    Get language name for LLM prompts.
    
    Args:
        conversation_id: Optional conversation ID
    
    Returns:
        Language name in English ("Lithuanian" or "English")
    """
    lang = get_language(conversation_id)
    return get_language_config(lang)["name"]


def get_agent_name(conversation_id: str | None = None) -> str:
    """
    Get agent name based on current language.
    
    Args:
        conversation_id: Optional conversation ID
    
    Returns:
        Agent name ("Andrius" for LT, "Andrew" for EN)
    """
    lang = get_language(conversation_id)
    return get_language_config(lang)["default_agent_name"]


def get_available_languages() -> list[dict]:
    """
    Get list of available languages.
    
    Returns:
        List of language info dicts
    """
    return [
        {
            "code": config["code"],
            "name": config["native_name"],
            "flag": config["flag"],
        }
        for config in LANGUAGE_CONFIG.values()
    ]


def is_valid_language(lang: str) -> bool:
    """Check if language code is valid."""
    return lang in LANGUAGE_CONFIG


# =============================================================================
# STATE SYNCHRONIZATION - Bridge between UI and Backend
# =============================================================================

def sync_language_from_state(state: Any) -> str:
    """
    Synchronize language service with conversation state.
    
    This should be called at the START of each node to ensure
    the language service uses the correct language from state.
    
    Args:
        state: LangGraph state (Pydantic model or dict)
    
    Returns:
        Current language code
    
    Usage in nodes:
        def some_node(state) -> dict:
            sync_language_from_state(state)  # First line!
            message = t("greeting.welcome")  # Now uses correct language
            ...
    """
    # Extract conversation_id
    if hasattr(state, "conversation_id"):
        conversation_id = state.conversation_id
    elif isinstance(state, dict):
        conversation_id = state.get("conversation_id")
    else:
        conversation_id = None
    
    # Extract language from state
    if hasattr(state, "language"):
        lang = state.language
    elif isinstance(state, dict):
        lang = state.get("language", DEFAULT_LANGUAGE)
    else:
        lang = DEFAULT_LANGUAGE
    
    # Validate and set
    if not is_valid_language(lang):
        logger.warning(f"Invalid language in state: '{lang}', using default")
        lang = DEFAULT_LANGUAGE
    
    # Set both global and per-conversation
    set_language(lang)  # Global fallback
    if conversation_id:
        set_language(lang, conversation_id)
    
    logger.debug(f"Synced language from state: {lang} (conv: {conversation_id})")
    
    return lang


def language_from_state(state: Any) -> str:
    """
    Get language from state without setting it.
    
    Useful for reading language without side effects.
    
    Args:
        state: LangGraph state
    
    Returns:
        Language code from state
    """
    if hasattr(state, "language"):
        lang = state.language
    elif isinstance(state, dict):
        lang = state.get("language", DEFAULT_LANGUAGE)
    else:
        lang = DEFAULT_LANGUAGE
    
    return lang if is_valid_language(lang) else DEFAULT_LANGUAGE


def clear_conversation_language(conversation_id: str) -> None:
    """
    Clear language setting when conversation ends.
    
    Call this in closing node to clean up.
    """
    _language_state.clear_conversation(conversation_id)


# =============================================================================
# LLM PROMPT HELPERS
# =============================================================================

def get_output_language_instruction(conversation_id: str | None = None) -> str:
    """
    Get instruction string for LLM to respond in correct language.
    
    Args:
        conversation_id: Optional conversation ID
    
    Returns:
        Instruction string for system prompt
    
    Usage:
        system_prompt = f'''
        You are a helpful assistant.
        {get_output_language_instruction()}
        '''
    """
    lang_name = get_language_name(conversation_id)
    return f"CRITICAL: Respond ONLY in {lang_name} language. All customer-facing text must be in {lang_name}."


def get_language_context(conversation_id: str | None = None) -> dict:
    """
    Get full language context for templates.
    
    Returns:
        Dict with language info for template formatting
    
    Usage:
        ctx = get_language_context()
        prompt = template.format(**ctx)
    """
    lang = get_language(conversation_id)
    config = get_language_config(lang)
    
    return {
        "language_code": lang,
        "output_language": config["name"],
        "agent_name": config["default_agent_name"],
        "language_native": config["native_name"],
    }
