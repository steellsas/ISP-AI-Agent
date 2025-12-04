"""
Phone Lookup Node - Find customer by phone number

Looks up customer in CRM by phone number.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.graph.state import add_message, _get_attr
from src.services.crm import get_customer_by_phone
from src.services.language_service import get_language
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# NODE FUNCTION
# =============================================================================


def phone_lookup_node(state: Any) -> dict:
    """
    Phone lookup node - find customer in CRM by phone number.

    This node doesn't generate messages - it's a silent lookup.
    Next node (address_confirmation or address_search) will communicate with user.

    Args:
        state: Current conversation state

    Returns:
        State update with customer data
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    phone_number = _get_attr(state, "phone_number")

    logger.info(f"[{conversation_id}] Phone lookup node started | phone={phone_number}")

    # Validate phone number
    if not phone_number:
        logger.error(f"[{conversation_id}] No phone number in state")
        return {"current_node": "phone_lookup", "last_error": "No phone number"}

    try:
        # Call CRM service
        result = get_customer_by_phone(phone_number)

        if result.get("success") and result.get("found"):
            # Customer found
            customer = result["customer"]
            addresses = result.get("addresses", [])

            customer_id = customer["customer_id"]
            customer_name = f"{customer['first_name']} {customer['last_name']}"

            logger.info(
                f"[{conversation_id}] Customer found | "
                f"customer_id={customer_id} | "
                f"name={customer_name} | "
                f"addresses_count={len(addresses)}"
            )

            return {
                "current_node": "phone_lookup",
                "customer_id": customer_id,
                "customer_name": customer_name,
                "customer_addresses": addresses,
                # Set flags based on addresses count
                "needs_address_confirmation": len(addresses) == 1,
                "needs_address_selection": len(addresses) > 1,
            }

        else:
            # Customer not found
            logger.warning(f"[{conversation_id}] Customer not found for phone: {phone_number}")

            return {
                "current_node": "phone_lookup",
                "customer_id": None,
                "customer_name": None,
                "customer_addresses": [],
            }

    except Exception as e:
        logger.error(f"[{conversation_id}] Phone lookup error: {e}", exc_info=True)

        return {
            "current_node": "phone_lookup",
            "customer_id": None,
            "customer_name": None,
            "customer_addresses": [],
            "last_error": str(e),
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================


def phone_lookup_router(state: Any) -> str:
    """
    Route after phone lookup.

    Returns:
        - "address_confirmation" → 1 address found
        - "address_selection" → multiple addresses
        - "address_search" → not found, ask for address
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    customer_id = _get_attr(state, "customer_id")
    addresses = _get_attr(state, "customer_addresses", [])

    if not customer_id:
        logger.info(f"[{conversation_id}] Router → address_search (customer not found)")
        return "address_search"

    if len(addresses) > 1:
        logger.info(f"[{conversation_id}] Router → address_selection ({len(addresses)} addresses)")
        return "address_selection"

    logger.info(f"[{conversation_id}] Router → address_confirmation (single address)")
    return "address_confirmation"
