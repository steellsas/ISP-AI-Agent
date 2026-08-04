"""API service settings (pydantic-settings, env prefix API_)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Host/runtime knobs for the FastAPI service. Engine behaviour flags
    (SOLVER_DRIVE, CLASSIFIER, TRACE_*) stay plain env vars the engine already
    reads — this class only configures the SERVICE around it."""

    model_config = SettingsConfigDict(env_prefix="API_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080
    # Idle sessions are ended (with a proper session_end trace) after this many
    # seconds without a turn — a forgotten browser tab must not hold a call open.
    session_ttl_seconds: int = 1800
    cleanup_interval_seconds: int = 60
    cors_origins: list[str] = ["*"]  # demo default; tighten in Phase 7


# USD per 1M tokens (input, output) — the dashboard's live call-cost counter.
# Model names are matched by prefix so "gpt-4o-mini-2024-07-18" hits "gpt-4o-mini".
MODEL_PRICES_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-haiku": (0.80, 4.00),
    "claude-sonnet": (3.00, 15.00),
}


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Best-effort cost of one LLM call; 0.0 for unknown/local models."""
    if not model:
        return 0.0
    low = model.lower()
    for prefix, (p_in, p_out) in MODEL_PRICES_USD_PER_1M.items():
        if prefix in low:
            return (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    return 0.0
