"""
Closing Node - End conversation gracefully

Provides appropriate closing message based on conversation outcome.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.graph.state import add_message, _get_attr
from src.services.language_service import get_language
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_customer_suffix(customer_name: str | None) -> str:
    """
    Get customer name suffix for closing message.

    Args:
        customer_name: Full customer name or None

    Returns:
        Formatted suffix like ", Jonas" or empty string
    """
    if not customer_name:
        return ""

    first_name = customer_name.split()[0] if customer_name else ""
    if first_name:
        return t("closing.customer_suffix.with_name", first_name=first_name)
    return ""


# =============================================================================
# NODE FUNCTION
# =============================================================================


def closing_node(state: Any) -> dict:
    """
    Closing node - ends conversation with appropriate message.

    Scenarios:
    1. Problem resolved → Thank and say goodbye
    2. Ticket created (escalation) → Confirm technician will contact
    3. Provider issue → Inform about automatic restoration
    4. Fallback → Generic goodbye

    Args:
        state: Current conversation state

    Returns:
        State update with closing message and conversation_ended=True
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Closing node started")

    try:
        # Get state values
        customer_name = _get_attr(state, "customer_name", "")
        problem_resolved = _get_attr(state, "problem_resolved", False)
        ticket_created = _get_attr(state, "ticket_created", False)
        ticket_id = _get_attr(state, "ticket_id")
        provider_issue_informed = _get_attr(state, "provider_issue_informed", False)

        # Get customer suffix for personalization
        customer_suffix = _get_customer_suffix(customer_name)

        # Determine closing message based on outcome
        if problem_resolved:
            # Happy path - problem solved
            closing_text = t("closing.resolved", customer_suffix=customer_suffix)
            outcome = "resolved"

        elif ticket_created and ticket_id:
            # Escalation path - technician will visit
            closing_text = t(
                "closing.escalated", customer_suffix=customer_suffix, ticket_id=ticket_id
            )
            outcome = "escalated"

        elif provider_issue_informed:
            # Provider issue - connection will restore automatically
            closing_text = t("closing.provider_issue", customer_suffix=customer_suffix)
            outcome = "provider_issue"

        else:
            # Fallback - generic goodbye
            closing_text = t("closing.fallback")
            outcome = "fallback"

        logger.info(
            f"[{conversation_id}] Closing conversation | "
            f"outcome={outcome} | resolved={problem_resolved} | "
            f"ticket={ticket_id} | lang={get_language()}"
        )

        # Create message
        message = add_message(role="assistant", content=closing_text, node="closing")

        return {
            "messages": [message],
            "current_node": "closing",
            "conversation_ended": True,
        }

    except Exception as e:
        logger.error(f"[{conversation_id}] Closing node error: {e}", exc_info=True)

        # Fallback closing
        fallback_text = t("closing.fallback", default="Ačiū, kad kreipėtės. Geros dienos!")

        message = add_message(role="assistant", content=fallback_text, node="closing")

        return {
            "messages": [message],
            "current_node": "closing",
            "conversation_ended": True,
            "last_error": str(e),
        }


# =============================================================================
# ROUTER (if needed)
# =============================================================================


def closing_router(state: Any) -> str:
    """
    Router after closing - always ends conversation.

    Returns:
        Always "end"
    """
    return "end"
