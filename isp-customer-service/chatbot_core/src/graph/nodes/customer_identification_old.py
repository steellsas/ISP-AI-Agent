"""
Customer Identification Node
Parse address from user message and find customer using CRM MCP service
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message, update_customer_info, get_last_user_message

logger = get_logger(__name__)


def customer_identification_node(state: ConversationState) -> ConversationState:
    """
    Customer identification node - Parse address and find customer.
    
    This node:
    1. Extracts address information from user message
    2. Calls CRM MCP service to find customer
    3. Updates state with customer information
    4. Handles cases where customer is not found
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with customer information
    """
    logger.info(f"[CustomerID] Processing for conversation {state['conversation_id']}")
    
    try:
        # Get last user message
        user_message = get_last_user_message(state)
        if not user_message:
            logger.warning("[CustomerID] No user message found")
            state = _request_address(state)
            return state
        
        # Parse address from message
        address = parse_address_from_message(user_message, state["language"])
        
        if not address or not address.get("city"):
            logger.info("[CustomerID] Could not parse address, requesting clarification")
            state = _request_address_clarification(state, user_message)
            return state
        
        logger.info(f"[CustomerID] Parsed address: {address}")
        
        # TODO: Call CRM MCP service to find customer
        # For now, simulate the lookup
        # This will be replaced with actual MCP client call:
        # from ...mcp_client import call_crm_tool
        # customer_result = await call_crm_tool("lookup_customer_by_address", address)
        
        customer_result = _simulate_customer_lookup(address)
        
        if customer_result.get("success"):
            # Customer found
            customer_data = customer_result["customer"]
            state = update_customer_info(state, customer_data)
            
            # Add confirmation message
            language = state["language"]
            confirmation = _create_confirmation_message(customer_data, language)
            state = add_message(state, "assistant", confirmation)
            
            logger.info(f"[CustomerID] Customer found: {customer_data.get('customer_id')}")
            
        else:
            # Customer not found
            error_type = customer_result.get("error", "customer_not_found")
            state = _handle_customer_not_found(state, error_type, customer_result)
            logger.warning(f"[CustomerID] Customer not found: {error_type}")
        
        # state["current_node"] = "customer_identification"
        # return state
        # Nustatome SEKANTĮ node pagal rezultatą
        if state["customer_identified"]:
            state["current_node"] = "problem_identification"  # ← Eina į problemą
        elif state["conversation_ended"]:
            state["current_node"] = "resolution"  # ← Baigia
        else:
            # Jei nepavyko rasti, bet tęsiame
            state["current_node"] = "problem_identification"  # ← Vis tiek tęsia

        return state
        
    except Exception as e:
        logger.error(f"[CustomerID] Error: {e}", exc_info=True)
        state = _handle_identification_error(state)
        return state


def parse_address_from_message(message: str, language: str = "lt") -> Optional[Dict[str, str]]:
    """
    Parse address components from user message.
    
    Looks for patterns like:
    - "Šiauliai, Tilžės 60-12"
    - "Tilžės gatvė 60, butas 12, Šiauliai"
    - "Kaunas Laisvės al. 5"
    
    Args:
        message: User message
        language: Language for parsing hints
        
    Returns:
        Dictionary with city, street, house_number, apartment_number or None
    """
    address = {}
    
    # Common Lithuanian cities
    cities = [
        "Vilnius", "Kaunas", "Klaipėda", "Šiauliai", "Siauliai", 
        "Panevėžys", "Panevezys", "Alytus", "Marijampolė", "Marijampole"
    ]
    
    # Try to find city
    message_lower = message.lower()
    for city in cities:
        if city.lower() in message_lower:
            address["city"] = city
            break
    
    # Extract street and house number using regex
    # Pattern: Street name (g./gatvė) + number + optional apartment
    
    # Pattern 1: "Tilžės 60-12" or "Tilzes g. 60-12"
    pattern1 = r'([A-ZĄČĘĖĮŠŲŪŽa-ząčęėįšųūž\s]+?)\s*(?:g\.|gatvė|gatve)?\s*(\d+)(?:-(\d+))?'
    
    # Pattern 2: "namo 60, buto 12" or "house 60, apartment 12"
    pattern2 = r'(?:namo|namas|house|nr\.?)\s*(\d+)(?:.*?(?:buto|butas|apartment|apt\.?)\s*(\d+))?'
    
    matches = re.search(pattern1, message, re.IGNORECASE)
    if matches:
        street_name = matches.group(1).strip()
        house_number = matches.group(2)
        apartment_number = matches.group(3)
        
        address["street"] = street_name
        address["house_number"] = house_number
        if apartment_number:
            address["apartment_number"] = apartment_number
    else:
        # Try pattern 2
        matches = re.search(pattern2, message, re.IGNORECASE)
        if matches:
            address["house_number"] = matches.group(1)
            if matches.group(2):
                address["apartment_number"] = matches.group(2)
    
    # Return address only if we have at least city and house number
    if address.get("city") and address.get("house_number"):
        return address
    
    return None


def _simulate_customer_lookup(address: Dict[str, str]) -> Dict[str, Any]:
    """
    Simulate customer lookup (temporary until MCP client is integrated).
    
    Args:
        address: Address dictionary
        
    Returns:
        Simulated customer result
    """
    # Simulate successful lookup for testing
    if address.get("city") == "Šiauliai" and address.get("house_number") == "60":
        return {
            "success": True,
            "customer": {
                "customer_id": "CUST001",
                "first_name": "Jonas",
                "last_name": "Jonaitis",
                "phone": "+37060012345",
                "email": "jonas@example.com",
                "address": {
                    "city": address["city"],
                    "street": address.get("street", "Tilžės g."),
                    "house_number": address["house_number"],
                    "apartment_number": address.get("apartment_number"),
                    "full_address": f"{address['city']}, {address.get('street', 'Tilžės g.')} {address['house_number']}"
                }
            }
        }
    else:
        return {
            "success": False,
            "error": "customer_not_found",
            "message": "Klientas nerastas šiuo adresu"
        }


def _request_address(state: ConversationState) -> ConversationState:
    """Request address from customer."""
    language = state["language"]
    
    if language == "lt":
        message = """Norėdamas Jums padėti, man reikia Jūsų adreso.

Prašau nurodyti:
• Miestą
• Gatvę
• Namo numerį
• Buto numerį (jei taikoma)

Pavyzdys: "Šiauliai, Tilžės 60-12" arba "Kaunas, Laisvės al. 5" """
    else:
        message = """To help you, I need your address.

Please provide:
• City
• Street
• House number
• Apartment number (if applicable)

Example: "Šiauliai, Tilžės 60-12" or "Kaunas, Laisvės al. 5" """
    
    return add_message(state, "assistant", message)


def _request_address_clarification(
    state: ConversationState,
    user_message: str
) -> ConversationState:
    """Request address clarification when parsing fails."""
    language = state["language"]
    
    if language == "lt":
        message = """Atsiprašau, negalėjau visiškai suprasti adreso.

Ar galite pateikti jį šiuo formatu?
• Miestas, Gatvė Namas-Butas

Pavyzdys: "Šiauliai, Tilžės 60-12" """
    else:
        message = """Sorry, I couldn't fully understand the address.

Could you provide it in this format?
• City, Street HouseNumber-ApartmentNumber

Example: "Šiauliai, Tilžės 60-12" """
    
    return add_message(state, "assistant", message)


def _create_confirmation_message(
    customer_data: Dict[str, Any],
    language: str
) -> str:
    """Create customer confirmation message."""
    name = customer_data.get("first_name", "")
    address = customer_data.get("address", {})
    full_address = address.get("full_address", "")
    
    if language == "lt":
        return f"""Puiku! Radau Jūsų duomenis. ✅

Vardas: {name}
Adresas: {full_address}

Dabar papasakokite apie problemą - kas neveikia ar veikia netinkamai?"""
    else:
        return f"""Great! I found your information. ✅

Name: {name}
Address: {full_address}

Now tell me about the problem - what's not working or working incorrectly?"""


def _handle_customer_not_found(
    state: ConversationState,
    error_type: str,
    result: Dict[str, Any]
) -> ConversationState:
    """Handle customer not found scenarios."""
    language = state["language"]
    
    # Mark as not identified but allow to continue
    state["customer_identified"] = False
    state["metadata"]["customer_lookup_failed"] = True
    state["metadata"]["customer_lookup_error"] = error_type
    
    if language == "lt":
        if error_type == "street_not_found":
            available_streets = result.get("available_streets", [])
            streets_text = ", ".join(available_streets[:5]) if available_streets else ""
            message = f"""Atsiprašau, tokios gatvės neradau sistemoje.

{f'Galbūt turėjote omenyje vieną iš šių: {streets_text}?' if streets_text else 'Patikrinkite gatvės pavadinimą.'}

Vis tiek galiu pabandyti padėti. Papasakokite apie problemą."""
        else:
            message = """Atsiprašau, negalėjau rasti Jūsų duomenų šiuo adresu.

Bet galiu pabandyti padėti! Papasakokite apie problemą:
• Internetas neveikia?
• Lėtas internetas?
• Televizija neveikia?"""
    else:
        message = """Sorry, I couldn't find your information at this address.

But I can still try to help! Tell me about the problem:
• Internet not working?
• Slow internet?
• TV not working?"""
    
    return add_message(state, "assistant", message)


def _handle_identification_error(state: ConversationState) -> ConversationState:
    """Handle unexpected errors during identification."""
    language = state["language"]
    
    if language == "lt":
        message = """Atsiprašau, įvyko techninė klaida.

Bet galiu pabandyti padėti! Aprašykite problemą ir pabandysime ją išspręsti."""
    else:
        message = """Sorry, a technical error occurred.

But I can still try to help! Describe the problem and we'll try to resolve it."""
    
    state["customer_identified"] = False
    return add_message(state, "assistant", message)
