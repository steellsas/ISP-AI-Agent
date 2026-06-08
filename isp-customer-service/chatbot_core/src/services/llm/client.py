"""
LLM Client

Main completion functions for calling LLMs with stats tracking.
"""

import json
import logging
import os
import re
import time

import litellm
from pydantic import BaseModel, ValidationError

from . import stats
from .models import calculate_cost
from .rate_limiter import get_rate_limiter
from .settings import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Model Info
# =============================================================================


def get_model_info(model: str) -> dict:
    """Get model info including whether it supports JSON mode."""
    # Models that support JSON mode
    json_mode_models = {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
        "gemini/gemini-1.5-pro",
        "gemini/gemini-1.5-flash",
        "gemini/gemini-2.0-flash-exp",
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


def _get_api_key(provider: str) -> str | None:
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
    code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find JSON object anywhere
    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from response: {content[:200]}")


def validate_json_response(data: dict, schema: type[BaseModel]) -> tuple[bool, str | None]:
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


def _resolve_params(
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    top_p: float | None,
) -> tuple[str, float, int, float]:
    """Fill in defaults from settings for any params left as None."""
    settings = get_settings()
    model = model or settings.model
    temperature = temperature if temperature is not None else settings.temperature
    max_tokens = max_tokens or settings.max_tokens
    top_p = top_p if top_p is not None else settings.top_p
    return model, temperature, max_tokens, top_p


def _configure_provider(model: str) -> str:
    """Resolve the provider for a model and export its API key for litellm."""
    provider = _get_provider(model)

    api_key = _get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key found for provider: {provider}")

    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = api_key

    return provider


def _execute_completion(kwargs: dict, model: str):
    """
    Run litellm.completion with rate limiting, retry, and stats tracking.

    This is the shared core behind both llm_completion (returns text) and
    llm_tool_completion (returns the message with tool_calls). Callers build
    the request kwargs; this function owns the cross-cutting concerns —
    rate-limit guard, retry loop, cost/latency stats — and returns the raw
    litellm response so each caller can extract what it needs.
    """
    global _last_call_stats

    settings = get_settings()

    # Rate limit: guard against runaway loops / cost blowup before hitting the API
    get_rate_limiter().check_or_raise()

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

            # Calculate cost (single source of truth: models.calculate_cost)
            cost = calculate_cost(model, input_tokens, output_tokens)

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

            # Wire the previously-dead infra: count the call against the rate
            # limiter and record it in aggregated session stats (cost/observability).
            get_rate_limiter().record_call()
            stats.record_call(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                cached=False,
                success=True,
            )

            logger.debug(
                f"LLM call: {model}, {input_tokens}+{output_tokens} tokens, ${cost:.4f}, {latency_ms:.0f}ms"
            )

            return response

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")

            if attempt < settings.max_retries - 1:
                delay = settings.retry_delay * (attempt + 1)
                time.sleep(delay)

    # Record failed call
    failed_latency_ms = (time.time() - start_time) * 1000
    _last_call_stats = {
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost": 0,
        "latency_ms": failed_latency_ms,
        "cached": False,
        "success": False,
        "error": str(last_error),
    }
    stats.record_call(
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
        latency_ms=failed_latency_ms,
        cached=False,
        success=False,
        error=str(last_error),
    )

    raise Exception(f"LLM call failed after {settings.max_retries} retries: {last_error}")


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
    model, temperature, max_tokens, top_p = _resolve_params(model, temperature, max_tokens, top_p)
    _configure_provider(model)

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

    response = _execute_completion(kwargs, model)
    return response.choices[0].message.content


def llm_tool_completion(
    messages: list[dict],
    tools: list[dict],
    tool_choice: str = "auto",
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
):
    """
    Call LLM with native function/tool calling and return the response message.

    Unlike llm_completion (which returns only the text content), this returns
    the full assistant message object so the caller can inspect both:
      - message.content    -> the natural-language reply (may be None when the
                              model decides to call a tool instead of talking)
      - message.tool_calls -> a list of structured tool calls, each with
                              .id, .function.name, .function.arguments (JSON str)

    This is the native-function-calling replacement for the ReAct regex parser:
    the model receives structured tool schemas (tools=...) and returns
    structured calls, eliminating the brittle "Action:/Action Input:" text
    parsing. The same shared infra (rate limit, retry, stats) is reused.

    Args:
        messages: Conversation so far (system/user/assistant/tool messages)
        tools: OpenAI function schemas, e.g. from agent.tools.get_tools_schema()
        tool_choice: "auto" (model decides), "none", "required", or a forced
            tool spec. Defaults to "auto" so the agent keeps full freedom over
            which tools to call and when.
        model: Model ID (uses settings default if None)
        temperature: Creativity (uses settings default if None)
        max_tokens: Max response length (uses settings default if None)
        top_p: Nucleus sampling (uses settings default if None)

    Returns:
        The assistant message object (litellm Message) with .content and
        .tool_calls.
    """
    model, temperature, max_tokens, top_p = _resolve_params(model, temperature, max_tokens, top_p)
    _configure_provider(model)

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tools": tools,
        "tool_choice": tool_choice,
    }

    if top_p != 1.0:
        kwargs["top_p"] = top_p

    response = _execute_completion(kwargs, model)
    return response.choices[0].message


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
                        messages = messages + [
                            {
                                "role": "user",
                                "content": f"Invalid JSON. Error: {error}. Respond with valid JSON only.",
                            }
                        ]
                        continue
                    raise ValueError(f"Invalid response: {error}")

            return result

        except ValueError as e:
            if "Could not extract JSON" in str(e):
                if retry_on_invalid and attempt == 0:
                    logger.warning("JSON parse failed, retrying")
                    messages = messages + [
                        {
                            "role": "user",
                            "content": "Your response was not valid JSON. Please respond ONLY with a JSON object, no other text.",
                        }
                    ]
                    continue
            raise

    raise ValueError("Failed to get valid JSON response")
