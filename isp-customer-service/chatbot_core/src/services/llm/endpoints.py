"""OpenAI-compatible endpoints for OPEN models: where `scaleway/<id>` and `local/<id>` go.

The model name carries the endpoint as a prefix, like `groq/` already does:

    scaleway/gemma-4-26b-a4b-it   Scaleway Generative APIs (Paris, EU) — the demo
    local/gemma4:26b              our own server: Ollama today, vLLM in production

Both speak the OpenAI API, so litellm gets `openai/<id>` plus the endpoint's base URL
and key. Moving from Scaleway to a local server is a model-name change, nothing else.

Open models (Gemma 4, Qwen3.x) THINK before answering unless told not to: up to
hundreds of hidden tokens — seconds on a phone call (measured 2026-10-06: Gemma 4 on
Scaleway spent its whole 300-token budget thinking and said nothing). `reasoning_effort:
"none"` switches that off on both Scaleway and Ollama; `LLM_REASONING_EFFORT` overrides
it (empty = send nothing, e.g. for gpt-oss, which only knows low/medium/high).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    base_url_env: str
    default_base_url: str
    key_env: str
    default_key: str | None = None  # a local server usually needs no real key


ENDPOINTS: dict[str, Endpoint] = {
    "scaleway": Endpoint("SCW_API_BASE", "https://api.scaleway.ai/v1", "SCW_SECRET_KEY"),
    "local": Endpoint(
        "LOCAL_LLM_BASE_URL", "http://localhost:11434/v1", "LOCAL_LLM_API_KEY", "local"
    ),
}


def endpoint_of(model: str) -> str | None:
    """'scaleway' / 'local' for an open-model name, None for everything else."""
    prefix, sep, _ = model.partition("/")
    return prefix if sep and prefix in ENDPOINTS else None


def api_key(name: str) -> str | None:
    ep = ENDPOINTS[name]
    return os.getenv(ep.key_env) or ep.default_key


def litellm_kwargs(model: str) -> dict:
    """The litellm arguments that send `model` to its endpoint; {} for a non-open model
    (litellm routes OpenAI / Groq / Gemini names itself)."""
    name = endpoint_of(model)
    if name is None:
        return {}
    ep = ENDPOINTS[name]
    kwargs = {
        "model": "openai/" + model.split("/", 1)[1],
        "api_base": os.getenv(ep.base_url_env) or ep.default_base_url,
        "api_key": api_key(name),
    }
    effort = os.getenv("LLM_REASONING_EFFORT", "none").strip()
    if effort:
        kwargs["extra_body"] = {"reasoning_effort": effort}
    return kwargs
