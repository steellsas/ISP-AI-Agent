# """
# Closing Node - End conversation gracefully
# """

# import sys
# import logging
# from pathlib import Path

# # Try shared logger
# try:
#     shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
#     if str(shared_path) not in sys.path:
#         sys.path.insert(0, str(shared_path))
#     from utils import get_logger
# except ImportError:
#     logging.basicConfig(level=logging.INFO)
#     def get_logger(name):
#         return logging.getLogger(name)

# from src.graph.state import add_message, _get_attr

# logger = get_logger(__name__)


# def closing_node(state) -> dict:
#     """
#     Closing node - ends conversation with appropriate message.
    
#     Behavior:
#     - If problem_resolved: Thank and say goodbye
#     - If escalation: Confirm technician will contact, say goodbye
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         State update with closing message
#     """
#     logger.info("=== Closing Node ===")
    
#     customer_name = _get_attr(state, "customer_name", "")
#     problem_resolved = _get_attr(state, "problem_resolved", False)
#     ticket_created = _get_attr(state, "ticket_created", False)
#     ticket_id = _get_attr(state, "ticket_id")
    
#     first_name = customer_name.split()[0] if customer_name else ""
    
#     if problem_resolved:
#         # Happy path - problem solved
#         closing_text = f"Džiaugiuosi, kad pavyko išspręsti problemą, {first_name}! " if first_name else "Džiaugiuosi, kad pavyko išspręsti problemą! "
#         closing_text += "Jei ateityje kiltų klausimų, drąsiai kreipkitės. Geros dienos!"
        
#     elif ticket_created and ticket_id:
#         # Escalation path - technician will come
#         closing_text = f"Ačiū už kantrybę, {first_name}. " if first_name else "Ačiū už kantrybę. "
#         closing_text += f"Technikas susisieks su jumis dėl vizito. Jūsų užklausos numeris: {ticket_id}. Geros dienos!"
        
#     else:
#         # Fallback
#         closing_text = "Ačiū, kad kreipėtės. Geros dienos!"
    
#     logger.info(f"Closing conversation. Resolved: {problem_resolved}, Ticket: {ticket_id}")
    
#     message = add_message(
#         role="assistant",
#         content=closing_text,
#         node="closing"
#     )
    
#     return {
#         "messages": [message],
#         "current_node": "closing",
#         "conversation_ended": True,
#     }



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
            closing_text = t(
                "closing.resolved",
                customer_suffix=customer_suffix
            )
            outcome = "resolved"
            
        elif ticket_created and ticket_id:
            # Escalation path - technician will visit
            closing_text = t(
                "closing.escalated",
                customer_suffix=customer_suffix,
                ticket_id=ticket_id
            )
            outcome = "escalated"
            
        elif provider_issue_informed:
            # Provider issue - connection will restore automatically
            closing_text = t(
                "closing.provider_issue",
                customer_suffix=customer_suffix
            )
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
        message = add_message(
            role="assistant",
            content=closing_text,
            node="closing"
        )
        
        return {
            "messages": [message],
            "current_node": "closing",
            "conversation_ended": True,
        }
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Closing node error: {e}", exc_info=True)
        
        # Fallback closing
        fallback_text = t(
            "closing.fallback",
            default="Ačiū, kad kreipėtės. Geros dienos!"
        )
        
        message = add_message(
            role="assistant",
            content=fallback_text,
            node="closing"
        )
        
        return {
            "messages": [message],
            "current_node": "closing",
            "conversation_ended": True,
            "last_error": str(e)
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
