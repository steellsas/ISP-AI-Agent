"""
Closing Node - End conversation gracefully
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

from src.graph.state import add_message, _get_attr

logger = get_logger(__name__)


def closing_node(state) -> dict:
    """
    Closing node - ends conversation with appropriate message.
    
    Behavior:
    - If problem_resolved: Thank and say goodbye
    - If escalation: Confirm technician will contact, say goodbye
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with closing message
    """
    logger.info("=== Closing Node ===")
    
    customer_name = _get_attr(state, "customer_name", "")
    problem_resolved = _get_attr(state, "problem_resolved", False)
    ticket_created = _get_attr(state, "ticket_created", False)
    ticket_id = _get_attr(state, "ticket_id")
    
    first_name = customer_name.split()[0] if customer_name else ""
    
    if problem_resolved:
        # Happy path - problem solved
        closing_text = f"Džiaugiuosi, kad pavyko išspręsti problemą, {first_name}! " if first_name else "Džiaugiuosi, kad pavyko išspręsti problemą! "
        closing_text += "Jei ateityje kiltų klausimų, drąsiai kreipkitės. Geros dienos!"
        
    elif ticket_created and ticket_id:
        # Escalation path - technician will come
        closing_text = f"Ačiū už kantrybę, {first_name}. " if first_name else "Ačiū už kantrybę. "
        closing_text += f"Technikas susisieks su jumis dėl vizito. Jūsų užklausos numeris: {ticket_id}. Geros dienos!"
        
    else:
        # Fallback
        closing_text = "Ačiū, kad kreipėtės. Geros dienos!"
    
    logger.info(f"Closing conversation. Resolved: {problem_resolved}, Ticket: {ticket_id}")
    
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