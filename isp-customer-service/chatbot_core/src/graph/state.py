"""
Conversation State - Pydantic schema for LangGraph workflow

Flat structure, minimal fields, easy to debug.
"""

from typing import Annotated, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import operator


class State(BaseModel):
    """
    Flat conversation state for ISP support agent.

    Design principles:
    - Flat structure (no deep nesting)
    - Minimal fields (add when needed)
    - Pydantic validation
    - Compatible with LangGraph
    """

    # === Conversation ===
    conversation_id: str
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # === Language (from UI settings) ===
    language: Literal["lt", "en"] = "lt"  # Default: Lithuanian

    # Messages - simple dicts with reducer for LangGraph
    messages: Annotated[list[dict], operator.add] = Field(default_factory=list)

    # Current position in workflow
    current_node: str = "start"

    # === Customer (from phone lookup) ===
    phone_number: str  # Ateina su skambučiu - privalomas

    # DB lookup rezultatai
    customer_id: str | None = None
    customer_name: str | None = None
    customer_addresses: list[dict] = Field(default_factory=list)  # Gali būti keli

    # Po adreso patvirtinimo
    confirmed_address_id: str | None = None
    confirmed_address: str | None = None  # Žmogui skaitomas adresas

    # === Problem ===
    problem_type: Literal["internet", "tv", "phone", "billing", "other"] | None = None
    problem_description: str | None = None

    # Problem Capture v2.1 - Qualifying context
    problem_context: dict = Field(default_factory=dict)

    qualifying_questions_asked: int = 0
    qualifying_answers: list[dict] = Field(default_factory=list)
    # Stores Q&A history: [
    #   {"question": "...", "answer": "...", "target_field": "duration", "understood": True},
    # ]

    problem_capture_complete: bool = False  # True when ready to proceed

    # === Workflow control ===
    needs_address_confirmation: bool = False
    needs_address_selection: bool = False  # Kai keli adresai
    address_confirmed: bool | None = None
    address_search_successful: bool | None = None

    # === Diagnostics ===
    diagnostics_completed: bool = False
    provider_issue_detected: bool = False  # Only CRITICAL issues (outages)
    needs_troubleshooting: bool = False
    provider_issue_informed: bool = False
    diagnostic_results: dict = Field(default_factory=dict)

    # === Troubleshooting ===
    troubleshooting_scenario_id: str | None = None
    troubleshooting_current_step: int = 1
    troubleshooting_completed_steps: list = Field(default_factory=list)
    troubleshooting_needs_escalation: bool = False
    troubleshooting_escalation_reason: str | None = None
    troubleshooting_skipped_steps: list = Field(default_factory=list)
    troubleshooting_checked_items: dict = Field(default_factory=dict)
    troubleshooting_failed: bool = False

    # Resolution
    problem_resolved: bool = False

    # === Ticket ===
    ticket_created: bool = False
    ticket_id: str | None = None
    ticket_type: str | None = None

    # === End state ===
    conversation_ended: bool = False

    # === Error tracking ===
    last_error: str | None = None
    llm_error_count: int = 0  # Track LLM failures to prevent infinite loops

    class Config:
        """Pydantic config."""

        extra = "allow"  # Leidžia pridėti papildomus laukus jei reikia


def create_initial_state(conversation_id: str, phone_number: str, language: str = "lt") -> dict:
    """
    Create initial state dict for LangGraph.

    Args:
        conversation_id: Unique conversation ID
        phone_number: Customer phone (from caller ID)
        language: UI language code ("lt" or "en")

    Returns:
        State as dict (LangGraph requirement)
    """
    # Validate language
    valid_languages = ["lt", "en"]
    if language not in valid_languages:
        language = "lt"  # Fallback to default

    state = State(conversation_id=conversation_id, phone_number=phone_number, language=language)
    return state.model_dump()


# === Message Helpers ===


def add_message(
    role: Literal["user", "assistant", "system"], content: str, node: str | None = None
) -> dict:
    """
    Create a message dict.

    Args:
        role: user, assistant, or system
        content: Message text
        node: Which node created this message

    Returns:
        Message dict ready to append to state.messages
    """
    return {"role": role, "content": content, "node": node, "timestamp": datetime.now().isoformat()}


def _get_messages(state) -> list[dict]:
    """Get messages from state (handles both Pydantic and dict)."""
    if hasattr(state, "messages"):
        return state.messages
    return state.get("messages", [])


def _get_attr(state, key: str, default=None):
    """Universal state attribute accessor (works with both Pydantic and dict)."""
    if hasattr(state, key):
        return getattr(state, key, default)
    elif isinstance(state, dict):
        return state.get(key, default)
    else:
        return default


def get_language_from_state(state) -> str:
    """Get language from state with fallback to default."""
    return _get_attr(state, "language", "lt")


def get_last_user_message(state) -> str | None:
    """Get last user message content."""
    messages = _get_messages(state)
    user_msgs = [m for m in messages if m["role"] == "user"]
    return user_msgs[-1]["content"] if user_msgs else None


def get_last_assistant_message(state) -> str | None:
    """Get last assistant message content."""
    messages = _get_messages(state)
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    return assistant_msgs[-1]["content"] if assistant_msgs else None


def get_conversation_for_llm(state) -> list[dict]:
    """
    Get messages formatted for LLM API call.

    Returns:
        List of {"role": ..., "content": ...} dicts
    """
    messages = _get_messages(state)
    return [{"role": m["role"], "content": m["content"]} for m in messages]


# === State Check Helpers ===


def is_customer_identified(state) -> bool:
    """Check if customer was found in DB."""
    return _get_attr(state, "customer_id") is not None


def is_address_confirmed(state) -> bool:
    """Check if address is confirmed."""
    return _get_attr(state, "address_confirmed", False)


def has_multiple_addresses(state) -> bool:
    """Check if customer has multiple addresses."""
    addresses = _get_attr(state, "customer_addresses", [])
    return len(addresses) > 1


def can_retry_troubleshooting(state) -> bool:
    """Check if we can try another troubleshooting step."""
    attempts = _get_attr(state, "troubleshooting_attempts", 0)
    max_attempts = _get_attr(state, "max_troubleshooting_attempts", 3)
    return attempts < max_attempts
