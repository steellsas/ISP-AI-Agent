"""
Create Ticket Node - Register support ticket in CRM
"""

import sys
import logging
from pathlib import Path

# Try shared logger
try:
    shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
    if str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from utils import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

from src.services.crm import create_support_ticket
from src.graph.state import add_message, _get_attr

logger = get_logger(__name__)


def create_ticket_node(state) -> dict:
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
    logger.info("=== Create Ticket Node ===")
    
    customer_id = _get_attr(state, "customer_id")
    customer_name = _get_attr(state, "customer_name", "")
    problem_description = _get_attr(state, "problem_description", "")
    problem_type = _get_attr(state, "problem_type", "internet")
    problem_resolved = _get_attr(state, "problem_resolved", False)
    escalation_reason = _get_attr(state, "troubleshooting_escalation_reason")
    completed_steps = _get_attr(state, "troubleshooting_completed_steps", [])
    
    if not customer_id:
        logger.error("No customer_id - cannot create ticket")
        return {
            "current_node": "create_ticket",
            "ticket_created": False,
            "last_error": "No customer ID"
        }
    
    # Determine ticket type and priority
    if problem_resolved:
        ticket_type = "resolved"
        priority = "low"
        summary = f"[Išspręsta] {problem_type}: {problem_description}"
        details = "Problema išspręsta per automatinį troubleshooting pokalbį."
        
        logger.info(f"Creating RESOLVED ticket for {customer_id}")
        
    else:
        ticket_type = "technician_visit"
        priority = "high"
        summary = f"[Reikalingas technikas] {problem_type}: {problem_description}"
        details = f"Problema neišspręsta per troubleshooting. Priežastis: {escalation_reason or 'nežinoma'}"
        
        logger.info(f"Creating TECHNICIAN_VISIT ticket for {customer_id}")
    
    # Create ticket
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
        logger.info(f"Ticket created: {ticket_id}")
        
        # Only add message if escalation (resolved tickets are silent)
        messages = []
        if not problem_resolved:
            # Inform customer about technician visit
            first_name = customer_name.split()[0] if customer_name else ""
            
            message = add_message(
                role="assistant",
                content=f"{first_name}, užregistravau jūsų užklausą. Mūsų technikas susisieks su jumis artimiausiu metu dėl vizito laiko suderinimo. Užklausos numeris: {ticket_id}.",
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
        logger.error(f"Ticket creation failed: {result.get('message')}")
        
        # Inform customer about error (only if escalation)
        messages = []
        if not problem_resolved:
            message = add_message(
                role="assistant",
                content="Atsiprašau, įvyko klaida registruojant užklausą. Prašome pabandyti vėliau arba paskambinti mūsų pagalbos linija.",
                node="create_ticket"
            )
            messages.append(message)
        
        return {
            "messages": messages,
            "current_node": "create_ticket",
            "ticket_created": False,
            "last_error": result.get("message")
        }