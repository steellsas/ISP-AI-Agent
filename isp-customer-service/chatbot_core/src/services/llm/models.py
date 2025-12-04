"""
LLM Models Registry

Available models with pricing and capabilities.
"""

from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Information about an LLM model."""

    id: str  # Model ID for API calls
    name: str  # Display name
    provider: str  # openai, google, anthropic
    input_cost_per_1k: float  # Cost per 1K input tokens (USD)
    output_cost_per_1k: float  # Cost per 1K output tokens (USD)
    max_tokens: int  # Max context window
    default_temperature: float = 0.3
    supports_json_mode: bool = True
    supports_vision: bool = False
    description: str = ""


# Available models registry
MODEL_REGISTRY: dict[str, ModelInfo] = {
    # =========================================================================
    # OpenAI Models
    # =========================================================================
    "gpt-4o": ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        input_cost_per_1k=0.005,
        output_cost_per_1k=0.015,
        max_tokens=128000,
        default_temperature=0.3,
        supports_json_mode=True,
        supports_vision=True,
        description="Most capable OpenAI model, multimodal",
    ),
    "gpt-4o-mini": ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
        max_tokens=128000,
        default_temperature=0.3,
        supports_json_mode=True,
        supports_vision=True,
        description="Fast and affordable, good for most tasks",
    ),
    # =========================================================================
    # Google Gemini Models
    # =========================================================================
    "gemini/gemini-2.5-pro": ModelInfo(
        id="gemini/gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="google",
        input_cost_per_1k=0.00125,
        output_cost_per_1k=0.005,
        max_tokens=1000000,
        default_temperature=0.3,
        supports_json_mode=True,
        supports_vision=True,
        description="Google's most capable model, huge context",
    ),
    "gemini/gemini-2.0-flash": ModelInfo(
        id="gemini/gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="google",
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
        max_tokens=1000000,
        default_temperature=0.3,
        supports_json_mode=True,
        supports_vision=True,
        description="Fast and cheap, good for simple tasks",
    ),
}


def get_available_models() -> list[dict]:
    """Get list of available models for UI dropdown."""
    return [
        {
            "id": model.id,
            "name": model.name,
            "provider": model.provider,
            "description": model.description,
            "cost_tier": _get_cost_tier(model.input_cost_per_1k),
        }
        for model in MODEL_REGISTRY.values()
    ]


def _get_cost_tier(cost_per_1k: float) -> str:
    """Get cost tier emoji for display."""
    if cost_per_1k > 0.003:
        return "💰💰"  # Expensive
    elif cost_per_1k > 0.001:
        return "💰"  # Medium
    elif cost_per_1k > 0.0005:
        return "💵"  # Affordable
    else:
        return "🆓"  # Very cheap


def get_models_by_provider(provider: str = None) -> list[dict]:
    """Get models filtered by provider."""
    models = get_available_models()
    if provider:
        models = [m for m in models if m["provider"] == provider]
    return models


def get_model_info(model_id: str) -> ModelInfo:
    """Get model info by ID."""
    if model_id not in MODEL_REGISTRY:
        # Return default if unknown
        return MODEL_REGISTRY["gpt-4o-mini"]
    return MODEL_REGISTRY[model_id]


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for a request in USD."""
    model = get_model_info(model_id)
    input_cost = (input_tokens / 1000) * model.input_cost_per_1k
    output_cost = (output_tokens / 1000) * model.output_cost_per_1k
    return input_cost + output_cost


def estimate_cost(model_id: str, prompt_chars: int, expected_output_chars: int = 500) -> float:
    """Estimate cost before making a call (rough: 4 chars ≈ 1 token)."""
    input_tokens = prompt_chars // 4
    output_tokens = expected_output_chars // 4
    return calculate_cost(model_id, input_tokens, output_tokens)
