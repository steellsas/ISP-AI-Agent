"""
LLM Client

Main completion functions for calling LLMs with stats tracking.
"""

import os
import re
import time
import json
import logging
from typing import Optional, Tuple
from pydantic import BaseModel, ValidationError

import litellm

from .settings import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Model Info
# =============================================================================

def get_model_info(model: str) -> dict:
    """Get model info including whether it supports JSON mode."""
    # Models that support JSON mode
    json_mode_models = {
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
        "gemini/gemini-1.5-pro", "gemini/gemini-1.5-flash", "gemini/gemini-2.0-flash-exp",
    }
    
    return {
        "model": model,
        "supports_json_mode": model in json_mode_models,
    }


# =============================================================================
# Stats Tracking
# =============================================================================

_last_call_stats = {}


def get_last_call_stats() -> dict:
    """Get stats from the last LLM call."""
    return _last_call_stats.copy()


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost based on model pricing."""
    # Pricing per 1M tokens (approximate)
    pricing = {
        # OpenAI
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        # Google
        "gemini/gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini/gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini/gemini-2.0-flash-exp": {"input": 0.10, "output": 0.40},
        # Anthropic
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }
    
    # Get pricing for model
    model_pricing = pricing.get(model, {"input": 0.50, "output": 1.50})
    
    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def _get_api_key(provider: str) -> Optional[str]:
    """Get API key for provider."""
    key_map = {
        "openai": "OPENAI_API_KEY",
        "google": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    env_var = key_map.get(provider, f"{provider.upper()}_API_KEY")
    return os.environ.get(env_var)


def _get_provider(model: str) -> str:
    """Determine provider from model name."""
    if model.startswith("gpt") or model.startswith("o1"):
        return "openai"
    elif model.startswith("gemini"):
        return "google"
    elif model.startswith("claude"):
        return "anthropic"
    return "openai"


# =============================================================================
# JSON Helpers
# =============================================================================

def extract_json_from_response(content: str) -> dict:
    """
    Extract JSON from LLM response.
    
    Handles:
    - Pure JSON responses
    - JSON in markdown code blocks
    - JSON mixed with text
    """
    if not content:
        raise ValueError("Empty response")
    
    content = content.strip()
    
    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON in markdown code block
    code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', content)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object anywhere
    json_match = re.search(r'\{[\s\S]*\}', content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not extract JSON from response: {content[:200]}")


def validate_json_response(data: dict, schema: type[BaseModel]) -> Tuple[bool, Optional[str]]:
    """
    Validate JSON against Pydantic schema.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        schema(**data)
        return True, None
    except ValidationError as e:
        return False, str(e)


# =============================================================================
# Main Completion Function
# =============================================================================

def llm_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
    response_format: dict = None,
) -> str:
    """
    Call LLM and return response text.
    
    Stats are stored in module-level _last_call_stats.
    
    Args:
        messages: List of {"role": ..., "content": ...}
        model: Model ID (uses settings default if None)
        temperature: Creativity 0-2 (uses settings default if None)
        max_tokens: Max response length (uses settings default if None)
        top_p: Nucleus sampling (uses settings default if None)
        response_format: Optional {"type": "json_object"} for JSON mode
    
    Returns:
        Response text content
    """
    global _last_call_stats
    
    settings = get_settings()
    
    # Apply defaults from settings
    model = model or settings.model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens
    top_p = top_p if top_p is not None else settings.top_p
    
    provider = _get_provider(model)
    
    # Get API key
    api_key = _get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key found for provider: {provider}")
    
    # Configure litellm
    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = api_key
    
    # Build request
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if top_p != 1.0:
        kwargs["top_p"] = top_p
    
    if response_format:
        kwargs["response_format"] = response_format
    
    # Make call with retry
    start_time = time.time()
    last_error = None
    
    for attempt in range(settings.max_retries):
        try:
            response = litellm.completion(**kwargs)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract token counts
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            
            # Calculate cost
            cost = _calculate_cost(model, input_tokens, output_tokens)
            
            # Get content
            content = response.choices[0].message.content
            
            # Store stats
            _last_call_stats = {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost": cost,
                "latency_ms": latency_ms,
                "cached": False,
                "success": True,
            }
            
            logger.debug(f"LLM call: {model}, {input_tokens}+{output_tokens} tokens, ${cost:.4f}, {latency_ms:.0f}ms")
            
            return content
            
        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            
            if attempt < settings.max_retries - 1:
                delay = settings.retry_delay * (attempt + 1)
                time.sleep(delay)
    
    # Record failed call
    _last_call_stats = {
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost": 0,
        "latency_ms": (time.time() - start_time) * 1000,
        "cached": False,
        "success": False,
        "error": str(last_error),
    }
    
    raise Exception(f"LLM call failed after {settings.max_retries} retries: {last_error}")


# =============================================================================
# JSON Completion
# =============================================================================

def llm_json_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    validate_schema: type[BaseModel] = None,
    retry_on_invalid: bool = True,
) -> dict:
    """
    Call LLM with JSON mode and return parsed dict.
    
    Args:
        messages: List of messages (prompt must ask for JSON!)
        model: Model ID
        temperature: Creativity
        max_tokens: Max response length
        validate_schema: Optional Pydantic model for validation
        retry_on_invalid: Retry with hint if JSON invalid
    
    Returns:
        Parsed JSON as dict
        
    Raises:
        ValueError: If JSON parsing fails after retries
    """
    settings = get_settings()
    model = model or settings.model
    model_info = get_model_info(model)
    
    # Use JSON mode if supported
    response_format = {"type": "json_object"} if model_info["supports_json_mode"] else None
    
    for attempt in range(2 if retry_on_invalid else 1):
        try:
            content = llm_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            
            # Parse JSON
            result = extract_json_from_response(content)
            
            # Validate if schema provided
            if validate_schema:
                is_valid, error = validate_json_response(result, validate_schema)
                if not is_valid:
                    if retry_on_invalid and attempt == 0:
                        logger.warning(f"JSON validation failed, retrying: {error}")
                        messages = messages + [{
                            "role": "user",
                            "content": f"Invalid JSON. Error: {error}. Respond with valid JSON only."
                        }]
                        continue
                    raise ValueError(f"Invalid response: {error}")
            
            return result
            
        except ValueError as e:
            if "Could not extract JSON" in str(e):
                if retry_on_invalid and attempt == 0:
                    logger.warning(f"JSON parse failed, retrying")
                    messages = messages + [{
                        "role": "user",
                        "content": "Your response was not valid JSON. Please respond ONLY with a JSON object, no other text."
                    }]
                    continue
            raise
    
    raise ValueError("Failed to get valid JSON response")