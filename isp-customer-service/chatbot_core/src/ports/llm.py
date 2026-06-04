"""LLM port — a text-in / text-out chat-completion backend."""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class Message(TypedDict):
    """One chat message. Matches the shape passed to litellm today."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    """A swappable chat-completion backend.

    Mirrors ``services/llm/client.llm_completion``. Any provider — OpenAI,
    Claude, Gemini, or a local Ollama model — implements this, so the agent
    core never imports a concrete SDK and switching model is a config/adapter
    swap (Phase 6).

    Phase 2 (native tool/function calling) will add a richer method that can
    return tool calls; this minimal text->text contract stays as the baseline.
    """

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        """Return the assistant's reply text for ``messages``."""
        ...
