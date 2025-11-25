"""
Phone Lookup Node - Find customer by phone number
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

from src.services.crm import get_customer_by_phone
from src.graph.state import add_message, _get_attr

logger = get_logger(__name__)


def phone_lookup_node(state) -> dict:
    """
    Phone lookup node - find customer in CRM by phone number.
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with customer data
    """
    logger.info("=== Phone Lookup Node ===")
    
    phone_number = _get_attr(state, "phone_number")
    logger.info(f"Looking up phone: {phone_number}")
    
    if not phone_number:
        logger.error("No phone number in state")
        return {
            "current_node": "phone_lookup",
            "last_error": "No phone number"
        }
    
    # Call CRM
    result = get_customer_by_phone(phone_number)
    
    if result.get("success") and result.get("found"):
        customer = result["customer"]
        addresses = result.get("addresses", [])
        
        logger.info(f"Found customer: {customer['customer_id']} - {customer['first_name']} {customer['last_name']}")
        logger.info(f"Addresses: {len(addresses)}")
        
        return {
            "current_node": "phone_lookup",
            "customer_id": customer["customer_id"],
            "customer_name": f"{customer['first_name']} {customer['last_name']}",
            "customer_addresses": addresses,
            # Set flags based on addresses count
            "needs_address_confirmation": len(addresses) == 1,
            "needs_address_selection": len(addresses) > 1,
        }
    else:
        # Customer not found
        logger.warning(f"Customer not found for phone: {phone_number}")
        return {
            "current_node": "phone_lookup",
            "customer_id": None,
            "customer_name": None,
            "customer_addresses": [],
        }


def phone_lookup_router(state) -> str:
    """
    Route after phone lookup.
    
    Returns:
        - "address_confirmation" → 1 address found
        - "address_selection" → multiple addresses
        - "address_search" → not found, ask for address
    """
    customer_id = _get_attr(state, "customer_id")
    addresses = _get_attr(state, "customer_addresses", [])
    
    if not customer_id:
        logger.info("Customer not found → address_search")
        return "address_search"
    
    if len(addresses) > 1:
        logger.info(f"Multiple addresses ({len(addresses)}) → address_selection")
        return "address_selection"
    
    logger.info("Single address → address_confirmation")
    return "address_confirmation"