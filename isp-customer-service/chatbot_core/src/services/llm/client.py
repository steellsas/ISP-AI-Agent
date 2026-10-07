"""
LLM Client

Main completion functions for calling LLMs with stats tracking.
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from contextvars import ContextVar

import litellm
from pydantic import BaseModel, ValidationError

from .. import ops_log
from . import endpoints, stats
from .models import calculate_cost
from .rate_limiter import RateLimitError, get_rate_limiter
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
        # Groq-hosted open models (groq/openai/gpt-oss-*, groq/qwen/…) support
        # response_format json_object across the board; so do Scaleway and vLLM/Ollama
        # (checked 2026-10-07: Gemma 4 on Scaleway returns clean JSON with it).
        "supports_json_mode": model in json_mode_models
        or model.startswith("groq/")
        or endpoints.endpoint_of(model) is not None,
    }


# =============================================================================
# Stats Tracking
# =============================================================================

_last_call_stats = {}


def get_last_call_stats() -> dict:
    """Get stats from the last LLM call."""
    return _last_call_stats.copy()


# The caller's observer for completed (non-streaming) calls: (role, stats) -> None.
# A context variable, so each conversation (and its background thread) reports its
# own calls — the module-level last-call stats are shared by every thread.
_observer: ContextVar[Callable[[str, dict], None] | None] = ContextVar("llm_observer", default=None)


@contextmanager
def observe_llm_calls(callback: Callable[[str, dict], None]):
    """Report every completed llm_completion / llm_json_completion call made inside
    this block to `callback(role, stats)` — including failed ones."""
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def _notify(role: str | None, call_stats: dict) -> None:
    callback = _observer.get()
    if callback is None:
        return
    try:
        callback(role or "other", dict(call_stats))
    except Exception:  # pragma: no cover - observability must never break a call
        logger.debug("llm observer failed", exc_info=True)


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
    endpoint = endpoints.endpoint_of(model)
    if endpoint:
        return endpoint  # scaleway/… or local/… — an OpenAI-compatible open-model server
    if model.startswith("groq/"):
        return "groq"  # litellm routes groq/<id> natively; key = GROQ_API_KEY
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


def _fallback_for(model: str) -> str | None:
    """LLM_FALLBACK_MODEL — the model that takes over when `model` fails (provider down,
    timeout, invalid JSON). None when unset or when `model` IS the fallback."""
    fallback = os.getenv("LLM_FALLBACK_MODEL", "").strip()
    return fallback if fallback and fallback != model else None


def _timeout(has_fallback: bool = False) -> float:
    """Seconds a request may take before it fails: a hung provider call must surface
    as an error the callers already handle (the sensors fall back to keywords, the
    speaker says its error line), never as a silent, endless turn.

    A model WITH a fallback gets a shorter leash (LLM_PRIMARY_TIMEOUT_S, default 8 s):
    waiting the full 30 s and only then asking the fallback would lose the caller."""
    if has_fallback:
        raw = os.getenv("LLM_PRIMARY_TIMEOUT_S", "").strip()
        try:
            return float(raw) if raw else 8.0
        except ValueError:
            return 8.0
    raw = os.getenv("LLM_TIMEOUT_S", "").strip()
    try:
        return float(raw) if raw else float(getattr(get_settings(), "request_timeout", 30.0))
    except ValueError:
        return 30.0


def _close_stream(stream) -> None:
    """Close a provider stream NOW, in this thread. Left to the garbage collector, an
    abandoned stream (the reply guard or a barge-in stops reading it) is finalized at an
    arbitrary moment — observed inside the NEXT request while httpx held its
    connection-pool lock: the finalizer then waited on that same lock forever (wave-0
    eval hang, 2026-09-18)."""
    for target in (getattr(stream, "completion_stream", None), stream):
        close = getattr(target, "close", None)
        if callable(close):
            with suppress(Exception):
                close()


def _configure_provider(model: str) -> str:
    """Resolve the provider for a model and export its API key for litellm."""
    provider = _get_provider(model)

    if endpoints.endpoint_of(model):
        # The key travels with the request (endpoints.litellm_kwargs), not via env.
        if not endpoints.api_key(provider):
            key_env = endpoints.ENDPOINTS[provider].key_env
            raise ValueError(f"No API key found for provider: {provider} (set {key_env})")
        return provider

    api_key = _get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key found for provider: {provider}")

    if provider == "openai":
        os.environ["OPENAI_API_KEY"] = api_key
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = api_key

    return provider


def _execute_completion(
    kwargs: dict, model: str, role: str | None = None, attempts: int | None = None
):
    """
    Run litellm.completion with rate limiting, retry, and stats tracking.

    This is the shared core behind llm_completion (returns text). Callers build
    the request kwargs; this function owns the cross-cutting concerns —
    rate-limit guard, retry loop, cost/latency stats — and returns the raw
    litellm response so each caller can extract what it needs.

    `attempts` overrides settings.max_retries: a model with a fallback gets ONE try —
    retrying a provider that is down only delays the hand-over.
    """
    global _last_call_stats

    settings = get_settings()
    attempts = attempts or settings.max_retries

    # Rate limit: guard against runaway loops / cost blowup before hitting the API
    get_rate_limiter().check_or_raise()

    start_time = time.time()
    last_error = None

    for attempt in range(attempts):
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

            _notify(role, _last_call_stats)
            return response

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")

            # Live 2026-09-11 (Groq gpt-oss-20b): json_validate_failed is a
            # DETERMINISTIC model/prompt mismatch — retrying burns the
            # provider's TPM budget and stalls the voice turn for seconds
            # (the retries then hit the rate limit). Fail fast; the callers
            # (understand/analyst/classifier) are fail-soft by design.
            if "json_validate_failed" in str(e):
                break

            if attempt < attempts - 1:
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

    _notify(role, _last_call_stats)
    raise Exception(f"LLM call failed after {attempts} retries: {last_error}")


def llm_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
    response_format: dict = None,
    role: str | None = None,
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
        role: What the call is for (perception, solver, analyst…) — reported to the
            observer (observe_llm_calls) with the call's stats

    Returns:
        Response text content
    """
    model, temperature, max_tokens, top_p = _resolve_params(model, temperature, max_tokens, top_p)
    fallback = _fallback_for(model)

    try:
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
        kwargs["timeout"] = _timeout(has_fallback=fallback is not None)

        if response_format:
            kwargs["response_format"] = response_format
        kwargs.update(endpoints.litellm_kwargs(model))

        response = _execute_completion(kwargs, model, role, attempts=1 if fallback else None)
    except RateLimitError:
        raise  # our own runaway-loop guard, not a provider fault: no fallback
    except Exception as e:
        if fallback is None:
            ops_log.event("llm", "call failed", logging.ERROR, model=model, role=role, error=e)
            raise
        ops_log.event("llm", "fallback", model=model, to=fallback, role=role, error=e)
        return llm_completion(
            messages,
            model=fallback,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            response_format=response_format,
            role=role,
        )
    return response.choices[0].message.content


def warm_up(model: str | None = None) -> float | None:
    """One 1-token request at app start, off the call path. Measured 2026-10-07: the
    first request of a process pays ~0.7 s (client + TLS) on top of litellm's own ~2.4 s
    import — it landed on the first caller's first turn (5.4 s to first audio). Later
    requests, even after 20 s idle, cost ~0.1 s extra. It doubles as a startup check: a
    wrong key or an unreachable provider shows in the ops log before anyone calls.
    Not counted in stats/rate limits. Returns the latency in seconds, None on failure."""
    model = model or get_settings().model
    start = time.time()
    try:
        _configure_provider(model)
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": "Labas"}],
            "max_tokens": 1,
            "timeout": 10.0,
        }
        kwargs.update(endpoints.litellm_kwargs(model))
        litellm.completion(**kwargs)
    except Exception as e:
        ops_log.event("llm", "warm-up failed", model=model, error=e)
        return None
    elapsed = time.time() - start
    ops_log.event("llm", "warm-up", logging.INFO, model=model, ms=round(elapsed * 1000))
    return elapsed


def _record_stream_stats(
    model: str,
    start_time: float,
    usage,
    messages: list[dict],
    content_parts: list[str],
    complete: bool,
) -> None:
    """The stats of one streamed call. A stream cut short (reply guard, barge-in) never
    gets the provider's usage chunk; without this it left the PREVIOUS call's stats in
    place and the speak call was booked with perception's tokens and latency (live
    2026-10-07). Then the tokens are counted locally and the record says `estimated`."""
    global _last_call_stats

    latency_ms = (time.time() - start_time) * 1000
    estimated = usage is None
    if usage is not None:
        input_tokens = usage.prompt_tokens or 0
        output_tokens = usage.completion_tokens or 0
    else:
        input_tokens = _count_tokens(model, messages=messages)
        output_tokens = _count_tokens(model, text="".join(content_parts))
    cost = calculate_cost(model, input_tokens, output_tokens)
    _last_call_stats = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost": cost,
        "latency_ms": latency_ms,
        "cached": False,
        "success": True,
        "estimated": estimated,
        "complete": complete,
    }
    try:
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
    except Exception:  # pragma: no cover - stats are best-effort
        pass


def _count_tokens(model: str, messages: list[dict] | None = None, text: str | None = None) -> int:
    """litellm's local token count (its default tokenizer for open models — close, not
    exact); a characters/4 guess if even that fails."""
    try:
        if messages is not None:
            return int(litellm.token_counter(model=model, messages=messages))
        return int(litellm.token_counter(model=model, text=text or ""))
    except Exception:
        raw = text if messages is None else " ".join(str(m.get("content", "")) for m in messages)
        return len(raw or "") // 4


def stream_tool_completion(
    messages: list[dict],
    tools: list[dict] | None,
    tool_choice: str = "auto",
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    top_p: float = None,
):
    """
    LLM call with native tool calling, streamed (Pillar C3).

    A GENERATOR that yields content tokens (str) as they arrive and RETURNS the
    final assistant message (with .content and .tool_calls) via the generator's
    return value — so callers do
    ``message = yield from stream_tool_completion(...)`` to both stream the text
    and get the structured result. Tool-call rounds emit no content (no yields);
    the final text reply streams token by token. Updates get_last_call_stats().
    """
    from types import SimpleNamespace

    model, temperature, max_tokens, top_p = _resolve_params(model, temperature, max_tokens, top_p)

    # Guard the LIVE voice path the same way the non-streaming path is guarded
    # (it had neither — a runaway loop could stream unmetered). Retries apply
    # only BEFORE the first token: once text is out, a mid-stream failure must
    # surface (replaying half a reply would double-speak it). The same rule decides
    # the fallback: the next model may take over only while nothing was said.
    settings = get_settings()
    get_rate_limiter().check_or_raise()

    start_time = time.time()
    content_parts: list[str] = []
    tc_acc: dict[int, dict] = {}
    usage = None

    fallback = _fallback_for(model)
    candidates = [model] + ([fallback] if fallback else [])
    for index, current in enumerate(candidates):
        is_last = index == len(candidates) - 1
        stream = None
        last_error: Exception | None = None
        try:
            _configure_provider(current)
        except Exception as e:  # e.g. no key for the primary — the fallback may have one
            last_error = e
        else:
            kwargs = {
                "model": current,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
                # A speaking call has no tools; providers reject tool_choice without them.
                "tool_choice": tool_choice if tools else None,
                "stream": True,
                "stream_options": {"include_usage": True},
                "timeout": _timeout(has_fallback=not is_last),
            }
            if top_p != 1.0:
                kwargs["top_p"] = top_p
            kwargs.update(endpoints.litellm_kwargs(current))

            for attempt in range(settings.max_retries if is_last else 1):
                try:
                    stream = litellm.completion(**kwargs)
                    break
                except Exception as e:  # connect-time failure — safe to retry
                    last_error = e
                    logger.warning(f"stream start failed (attempt {attempt + 1}): {e}")
                    if is_last:
                        time.sleep(settings.retry_delay * (attempt + 1))
        if stream is None:
            if is_last:
                ops_log.event(
                    "llm", "stream failed", logging.ERROR, model=current, error=last_error
                )
                raise last_error  # type: ignore[misc]
            ops_log.event(
                "llm", "fallback", model=current, to=candidates[-1], role="speak", error=last_error
            )
            continue

        try:
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = choices[0].delta
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                    yield delta.content
                for tc in getattr(delta, "tool_calls", None) or []:
                    acc = tc_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if getattr(tc, "id", None):
                        acc["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn and getattr(fn, "name", None):
                        acc["name"] = fn.name
                    if fn and getattr(fn, "arguments", None):
                        acc["arguments"] += fn.arguments
        except GeneratorExit:
            # The reader stopped early (reply guard, barge-in): book THIS call anyway.
            _record_stream_stats(
                current, start_time, usage, messages, content_parts, complete=False
            )
            raise
        except Exception as e:
            if content_parts or tc_acc or is_last:
                ops_log.event("llm", "stream broke", logging.ERROR, model=current, error=e)
                raise
            # Failed before its first token (timeout, provider error in the first
            # chunk): nothing was spoken, so the fallback can still answer.
            ops_log.event(
                "llm", "fallback", model=current, to=candidates[-1], role="speak", error=e
            )
            continue
        finally:
            # A reader that stops early (reply guard, barge-in) closes this generator; the
            # provider stream must be closed with it, here and now.
            _close_stream(stream)
        model = current  # the model that actually answered — stats and cost follow it
        break

    _record_stream_stats(model, start_time, usage, messages, content_parts, complete=True)

    tool_calls = [
        SimpleNamespace(
            id=tc_acc[i]["id"],
            type="function",
            function=SimpleNamespace(name=tc_acc[i]["name"], arguments=tc_acc[i]["arguments"]),
        )
        for i in sorted(tc_acc)
    ] or None
    return SimpleNamespace(content=("".join(content_parts) or None), tool_calls=tool_calls)


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
    role: str | None = None,
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

    A provider failure already falls back inside llm_completion; here the fallback
    also covers a model that ANSWERS but cannot keep the JSON shape (twice in a row).
    """
    model = model or get_settings().model
    try:
        return _json_completion(
            messages, model, temperature, max_tokens, validate_schema, retry_on_invalid, role
        )
    except ValueError as e:
        fallback = _fallback_for(model)
        if fallback is None:
            raise
        ops_log.event("llm", "fallback: invalid JSON", model=model, to=fallback, role=role, error=e)
        return _json_completion(
            messages, fallback, temperature, max_tokens, validate_schema, retry_on_invalid, role
        )


def _json_completion(
    messages: list[dict],
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    validate_schema: type[BaseModel] | None,
    retry_on_invalid: bool,
    role: str | None,
) -> dict:
    """One model's JSON attempt (with its own invalid-JSON retry)."""
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
                role=role,
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
