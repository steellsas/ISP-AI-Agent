"""
Create Ticket Node - Register support ticket in CRM

Creates tickets for both resolved issues (silent) and escalations.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.graph.state import add_message, _get_attr
from src.services.crm import create_support_ticket
from src.services.language_service import get_language
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# NODE FUNCTION
# =============================================================================

def create_ticket_node(state: Any) -> dict:
    """
    Create ticket node - registers support ticket in CRM.
    
    Behavior:
    - If problem_resolved: Create "resolved" ticket silently (no message to customer)
    - If needs_escalation: Create "technician_visit" ticket and inform customer
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with ticket info
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Create ticket node started")
    
    # Get required state values
    customer_id = _get_attr(state, "customer_id")
    customer_name = _get_attr(state, "customer_name", "")
    problem_description = _get_attr(state, "problem_description", "")
    problem_type = _get_attr(state, "problem_type", "internet")
    problem_resolved = _get_attr(state, "problem_resolved", False)
    escalation_reason = _get_attr(state, "troubleshooting_escalation_reason")
    completed_steps = _get_attr(state, "troubleshooting_completed_steps", [])
    
    # Validate customer_id
    if not customer_id:
        logger.error(f"[{conversation_id}] No customer_id - cannot create ticket")
        return {
            "current_node": "create_ticket",
            "ticket_created": False,
            "last_error": "No customer ID"
        }
    
    try:
        # Determine ticket type and priority
        if problem_resolved:
            ticket_type = "resolved"
            priority = "low"
            summary = f"[Resolved] {problem_type}: {problem_description}"
            details = "Problem resolved via automated troubleshooting conversation."
            
            logger.info(f"[{conversation_id}] Creating RESOLVED ticket")
            
        else:
            ticket_type = "technician_visit"
            priority = "high"
            summary = f"[Technician needed] {problem_type}: {problem_description}"
            details = f"Problem not resolved via troubleshooting. Reason: {escalation_reason or 'unknown'}"
            
            logger.info(f"[{conversation_id}] Creating TECHNICIAN_VISIT ticket")
        
        # Create ticket via CRM service
        result = create_support_ticket(
            customer_id=customer_id,
            ticket_type=ticket_type,
            summary=summary,
            details=details,
            priority=priority,
            troubleshooting_steps=completed_steps
        )
        
        if result.get("success"):
            ticket_id = result.get("ticket_id")
            
            logger.info(
                f"[{conversation_id}] Ticket created | "
                f"ticket_id={ticket_id} | type={ticket_type} | "
                f"lang={get_language()}"
            )
            
            # Build response message (only for escalation)
            messages = []
            if not problem_resolved:
                # Get first name for personalization
                first_name = customer_name.split()[0] if customer_name else ""
                
                message_text = t(
                    "ticket.created",
                    customer_name=first_name,
                    ticket_id=ticket_id
                )
                
                message = add_message(
                    role="assistant",
                    content=message_text,
                    node="create_ticket"
                )
                messages.append(message)
            
            return {
                "messages": messages,
                "current_node": "create_ticket",
                "ticket_created": True,
                "ticket_id": ticket_id,
                "ticket_type": ticket_type,
            }
        
        else:
            # Ticket creation failed
            error_msg = result.get("message", "Unknown error")
            logger.error(f"[{conversation_id}] Ticket creation failed: {error_msg}")
            
            # Inform customer only if escalation
            messages = []
            if not problem_resolved:
                message = add_message(
                    role="assistant",
                    content=t("ticket.creation_failed"),
                    node="create_ticket"
                )
                messages.append(message)
            
            return {
                "messages": messages,
                "current_node": "create_ticket",
                "ticket_created": False,
                "last_error": error_msg
            }
            
    except Exception as e:
        logger.error(f"[{conversation_id}] Create ticket error: {e}", exc_info=True)
        
        # Inform customer only if escalation
        messages = []
        if not problem_resolved:
            message = add_message(
                role="assistant",
                content=t("ticket.creation_failed"),
                node="create_ticket"
            )
            messages.append(message)
        
        return {
            "messages": messages,
            "current_node": "create_ticket",
            "ticket_created": False,
            "last_error": str(e)
        }
