"""
LLM Client

Main completion functions for calling LLMs.
"""

import os
import time
import logging
from typing import Optional
from pydantic import BaseModel

import litellm

from .models import get_model_info, calculate_cost
from .settings import get_settings
from .stats import record_call, get_session_stats
from .rate_limiter import get_rate_limiter, RateLimitError
from .cache import get_cache
from .utils import (
    get_api_key,
    extract_json_from_response,
    validate_json_response,
    LLMError,
)

logger = logging.getLogger(__name__)

# Stats callbacks for UI integration
_stats_callbacks = []


def register_stats_callback(callback):
    """Register callback for LLM stats updates."""
    global _stats_callbacks
    if callback not in _stats_callbacks:
        _stats_callbacks.append(callback)


def unregister_stats_callback(callback):
    """Remove callback."""
    global _stats_callbacks
    if callback in _stats_callbacks:
        _stats_callbacks.remove(callback)


def _notify_callbacks(data: dict):
    """Notify all registered callbacks."""
    for callback in _stats_callbacks:
        try:
            callback(data)
        except Exception as e:
            logger.warning(f"Stats callback error: {e}")



def llm_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
    response_format: dict = None,
    use_cache: bool = None,
) -> str:
    """
    Call LLM and return response text.
    
    Args:
        messages: List of {"role": ..., "content": ...}
        model: Model ID (uses settings default if None)
        temperature: Creativity 0-2 (uses settings default if None)
        max_tokens: Max response length (uses settings default if None)
        top_p: Nucleus sampling (uses settings default if None)
        response_format: Optional {"type": "json_object"} for JSON mode
        use_cache: Whether to use caching (uses settings default if None)
    
    Returns:
        Response text content
        
    Raises:
        RateLimitError: If rate limit exceeded
        LLMError: If API call fails
    """
    settings = get_settings()
    
    # Apply defaults from settings
    model = model or settings.model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens
    top_p = top_p if top_p is not None else settings.top_p
    use_cache = use_cache if use_cache is not None else settings.enable_cache
    
    model_info = get_model_info(model)
    cache = get_cache()
    rate_limiter = get_rate_limiter()
    
    # Check rate limit
    rate_limiter.check_or_raise()
    
    # Check cache
    if use_cache:
        cached = cache.get(messages, model, temperature)
        if cached:
            record_call(
                model=model,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                latency_ms=0,
                cached=True,
            )
            return cached
    
    # Get API key and configure litellm
    api_key = get_api_key(model_info.provider)
    _configure_litellm(model_info.provider, api_key)
    
    # Build request
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if top_p != 1.0:
        kwargs["top_p"] = top_p
    
    if response_format and model_info.supports_json_mode:
        kwargs["response_format"] = response_format
    
    # Make call with retry
    start_time = time.time()
    last_error = None
    
    for attempt in range(settings.max_retries):
        try:
            logger.debug(f"LLM call 22: model={model}, attempt={attempt + 1}")
            
            response = litellm.completion(**kwargs)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract token counts
       
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            
            # Calculate cost
            cost = calculate_cost(model, input_tokens, output_tokens)
            
            # Get content
            content = response.choices[0].message.content


            
            # Record call
            rate_limiter.record_call()
            print(f"DEBUG CLIENT: Recording call - tokens={input_tokens}+{output_tokens}, cost=${cost:.6f}")
            record_call(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            )
            print(f"DEBUG CLIENT: Total calls now = {get_session_stats().total_calls}")
            print(f"DEBUG CLIENT: stats id = {id(get_session_stats())}, total_calls = {get_session_stats().total_calls}")


            # Notify UI callbacks
            _notify_callbacks({
                "type": "llm_call",
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "latency_ms": latency_ms,
                "cached": False,
                "success": True,
            })
            # Cache response
            if use_cache:
                cache.set(messages, model, temperature, content)
            
            return content
            
        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            
            if attempt < settings.max_retries - 1:
                delay = settings.retry_delay * (attempt + 1)
                time.sleep(delay)
    
    # Record failed call

    record_call(
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
        latency_ms=(time.time() - start_time) * 1000,
        success=False,
        error=str(last_error),
    )
    
    raise LLMError(f"LLM call failed after {settings.max_retries} retries: {last_error}")


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
    response_format = {"type": "json_object"} if model_info.supports_json_mode else None
    
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
    
    raise ValueError("Failed to get valid JSON response after retries")


def _configure_litellm(provider: str, api_key: str):
    """Configure litellm for the provider."""
    if provider == "openai":
        litellm.api_key = api_key
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = api_key
    elif provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = api_key


# =============================================================================
# Convenience Functions
# =============================================================================

def quick_completion(prompt: str, model: str = None) -> str:
    """Quick single-prompt completion."""
    return llm_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
    )


def quick_json(prompt: str, model: str = None) -> dict:
    """Quick JSON completion."""
    return llm_json_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
    )
