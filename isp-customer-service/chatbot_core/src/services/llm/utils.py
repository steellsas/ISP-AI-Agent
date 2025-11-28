"""
LLM Utilities

API key management, JSON extraction, response validation.
"""

import os
import re
import json
import logging
from typing import Optional
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# =============================================================================
# API Key Management
# =============================================================================

# Environment variable names for each provider
API_KEY_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def get_api_key(provider: str) -> str:
    """
    Get API key for provider.
    
    Args:
        provider: Provider name (openai, google, anthropic)
        
    Returns:
        API key string
        
    Raises:
        ValueError: If API key not found
    """
    env_var = API_KEY_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
    
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(f"{env_var} not found in environment")
    
    return api_key


def check_api_keys() -> dict[str, bool]:
    """
    Check which API keys are available.
    
    Returns:
        Dict of provider -> available (True/False)
    """
    keys = {}
    for provider in ["openai", "google", "anthropic"]:
        try:
            get_api_key(provider)
            keys[provider] = True
        except ValueError:
            keys[provider] = False
    return keys


def get_available_providers() -> list[str]:
    """Get list of providers with valid API keys."""
    keys = check_api_keys()
    return [provider for provider, available in keys.items() if available]


def mask_api_key(key: str) -> str:
    """Mask API key for logging (show first 4 and last 4 chars)."""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


# =============================================================================
# JSON Extraction & Validation
# =============================================================================

def extract_json_from_response(content: str) -> dict:
    """
    Extract JSON from LLM response, handling various formats.
    
    Handles:
    - Direct JSON
    - JSON in markdown code blocks (```json ... ```)
    - JSON embedded in text
    
    Args:
        content: Raw LLM response
        
    Returns:
        Parsed JSON dict
        
    Raises:
        ValueError: If JSON cannot be extracted
    """
    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Try to extract from markdown code block
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object in text
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON array
    json_match = re.search(r'\[[\s\S]*\]', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not extract JSON from response: {content[:200]}...")


def validate_json_response(
    response: dict, 
    schema: type[BaseModel] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate JSON response against Pydantic schema.
    
    Args:
        response: Parsed JSON dict
        schema: Optional Pydantic model class for validation
        
    Returns:
        (is_valid, error_message or None)
    """
    if schema is None:
        return True, None
    
    try:
        schema(**response)
        return True, None
    except ValidationError as e:
        return False, str(e)


def safe_json_loads(content: str, default: dict = None) -> dict:
    """
    Safely parse JSON with fallback to default.
    
    Args:
        content: JSON string
        default: Default value if parsing fails
        
    Returns:
        Parsed dict or default
    """
    if default is None:
        default = {}
    
    try:
        return extract_json_from_response(content)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"JSON parse failed: {e}")
        return default


# =============================================================================
# Exceptions
# =============================================================================

class LLMError(Exception):
    """General LLM error."""
    pass


class JSONParseError(LLMError):
    """Error parsing JSON from LLM response."""
    pass


class ValidationError(LLMError):
    """Error validating LLM response."""
    pass
