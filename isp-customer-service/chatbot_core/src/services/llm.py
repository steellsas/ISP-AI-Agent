# """

"""
LLM Service - Wrapper for LLM calls using litellm

Uses shared config for API keys (with fallback).
"""

import os
import sys
from pathlib import Path
from typing import Any
import json
import logging

# Try to import from shared module
try:
    shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
    if str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from utils import get_logger, get_config
    HAS_SHARED = True
except ImportError:
    HAS_SHARED = False
    # Fallback logger
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

import litellm

logger = get_logger(__name__)


def get_openai_api_key() -> str:
    """Get OpenAI API key from shared config or environment."""
    if HAS_SHARED:
        config = get_config()
        return config.openai_api_key
    else:
        # Fallback to environment variable
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        return api_key


def llm_completion(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 500,
    response_format: dict | None = None
) -> str:
    """
    Call LLM and return response text.
    
    Args:
        messages: List of {"role": ..., "content": ...}
        model: Model name
        temperature: Creativity (0-1)
        max_tokens: Max response length
        response_format: Optional {"type": "json_object"} for JSON mode
    
    Returns:
        Response text content
    """
    api_key = get_openai_api_key()
    
    # Set API key for litellm
    litellm.api_key = api_key
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if response_format:
        kwargs["response_format"] = response_format
    
    logger.debug(f"LLM call: model={model}, messages={len(messages)}")
    
    response = litellm.completion(**kwargs)
    
    content = response.choices[0].message.content
    logger.debug(f"LLM response: {content[:100]}...")
    
    return content


def llm_json_completion(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 500,
) -> dict:
    """
    Call LLM with JSON mode and return parsed dict.
    
    Args:
        messages: List of messages (must ask for JSON in prompt!)
        model: Model name
        temperature: Creativity
        max_tokens: Max response length
    
    Returns:
        Parsed JSON as dict
    """
    content = llm_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"}
    )
    
    return json.loads(content)