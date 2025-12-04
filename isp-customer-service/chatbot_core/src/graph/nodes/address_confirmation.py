"""
Address Confirmation Node - Confirm customer's address

Asks customer to confirm their address and analyzes response.
Uses LLM for natural language understanding.
Supports multiple languages via translation service.
"""

import logging
from typing import Any
from pydantic import BaseModel

from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr
from src.services.llm import llm_json_completion
from src.services.language_service import get_language, get_language_name
from src.services.translation_service import t

logger = logging.getLogger(__name__)


class AddressConfirmationAnalysis(BaseModel):
    """LLM response schema for address confirmation."""
    confirmed: bool = False
    rejected: bool = False
    correction_provided: str | None = None  
    clarification_needed: bool = False
    response_message: str  


def _build_confirmation_prompt(address: str) -> str:
    """
    Build system prompt for address confirmation analysis.
    
    Prompt is in English, but instructs LLM to respond in target language.
    
    Args:
        address: The address to confirm
        
    Returns:
        System prompt string
    """
    output_language = get_language_name()
    
    return f"""You are an ISP customer service assistant.
The customer needs to confirm their address.

Suggested address: {address}

Analyze the customer's response and determine:
1. Did they CONFIRM the address? (yes, correct, that's right, etc.)
2. Did they REJECT the address? (no, wrong, different address, etc.)
3. Did they provide a CORRECTION/different address?
4. Do you need CLARIFICATION?

Respond in JSON format:
{{
    "confirmed": true | false,
    "rejected": true | false,
    "correction_provided": "new address or null",
    "clarification_needed": true | false,
    "response_message": "response to customer in {output_language}"
}}

Examples:
- "yes" → confirmed=true, response_message="Great, address confirmed. Checking your connection..."
- "correct" → confirmed=true
- "no, I live in Vilnius" → rejected=true, correction_provided="Vilnius"
- "same, but apartment 7" → rejected=true, correction_provided="apartment 7"
- "hmm not sure" → clarification_needed=true, response_message="Is your address really {{address}}?"

CRITICAL: response_message MUST be in {output_language} language.
Be friendly and professional."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_address_string(state: Any) -> str:
    """Get formatted address from state."""
    addresses = _get_attr(state, "customer_addresses", [])
    if addresses:
        addr = addresses[0]
        return addr.get("full_address") or f"{addr.get('city', '')}, {addr.get('street', '')} {addr.get('house_number', '')}"
    return t("address.unknown", default="unknown address")


def _needs_confirmation_question(state: Any) -> bool:
    """Check if we need to ask confirmation question (no user response yet)."""
    messages = _get_messages(state)
    
    for msg in reversed(messages):
        if msg.get("node") == "address_confirmation" and msg["role"] == "assistant":
            idx = messages.index(msg)
            for later_msg in messages[idx+1:]:
                if later_msg["role"] == "user":
                    return False  
            return True 
    return True  


# =============================================================================
# NODE FUNCTION
# =============================================================================

def address_confirmation_node(state: Any) -> dict:
    """
    Address confirmation node - asks and verifies address.
    
    Flow:
    1. First call: Ask confirmation question
    2. Second call: Analyze user response with LLM
    
    Args:
        state: Current conversation state
        
    Returns:
        State update dict
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Address confirmation node started")
    
    address = _get_address_string(state)
    customer_name = _get_attr(state, "customer_name", "")
    first_name = customer_name.split()[0] if customer_name else ""
    
    try:
        if _needs_confirmation_question(state):
            logger.info(f"[{conversation_id}] Asking confirmation for address: {address}")
            
            if first_name:
                question = t("address.confirmation_ask", customer_name=first_name, address=address)
            else:
                question = t("address.confirmation_ask_short", address=address)
            
            message = add_message(
                role="assistant",
                content=question,
                node="address_confirmation"
            )
            
            return {
                "messages": [message],
                "current_node": "address_confirmation",
            }
        
        # Analyze user response
        user_message = get_last_user_message(state)
        logger.info(f"[{conversation_id}] Analyzing user response: {user_message[:50]}...")
        
        system_prompt = _build_confirmation_prompt(address)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = llm_json_completion(
            messages=messages,
            temperature=0.2,
            max_tokens=200
        )
        
        analysis = AddressConfirmationAnalysis(**response)
        
        logger.info(
            f"[{conversation_id}] Analysis result | "
            f"confirmed={analysis.confirmed} | "
            f"rejected={analysis.rejected} | "
            f"clarification={analysis.clarification_needed}"
        )
        
        # Create response message
        message = add_message(
            role="assistant",
            content=analysis.response_message,
            node="address_confirmation"
        )
        
        # Update state based on analysis
        if analysis.confirmed:
            addresses = _get_attr(state, "customer_addresses", [])
            confirmed_addr = addresses[0] if addresses else {}
            
            logger.info(f"[{conversation_id}] Address confirmed | lang={get_language()}")
            
            return {
                "messages": [message],
                "current_node": "address_confirmation",
                "address_confirmed": True,
                "confirmed_address_id": confirmed_addr.get("address_id"),
                "confirmed_address": address,
            }
        
        elif analysis.rejected:
            logger.info(f"[{conversation_id}] Address rejected, correction: {analysis.correction_provided}")
            
            # Don't add message - address_search will ask for address
            return {
                "messages": [],
                "current_node": "address_confirmation",
                "address_confirmed": False,
                "address_correction": analysis.correction_provided,
            }
        
        else:
            # Need clarification - will loop back
            logger.info(f"[{conversation_id}] Needs clarification")
            
            return {
                "messages": [message],
                "current_node": "address_confirmation",
            }
            
    except Exception as e:
        logger.error(f"[{conversation_id}] Address confirmation error: {e}", exc_info=True)
        
        # Fallback - ask again
        fallback_question = t(
            "address.confirmation_ask_short",
            default=f"Ar jūsų adresas yra {address}?",
            address=address
        )
        
        fallback_message = add_message(
            role="assistant",
            content=fallback_question,
            node="address_confirmation"
        )
        
        return {
            "messages": [fallback_message],
            "current_node": "address_confirmation",
            "last_error": str(e)
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================

def address_confirmation_router(state: Any) -> str:
    """
    Route after address confirmation.
    
    Returns:
        - "address_confirmation" → need clarification (loop)
        - "diagnostics" → address confirmed
        - "address_search" → address rejected
        - "end" → waiting for user input
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    address_confirmed = _get_attr(state, "address_confirmed")
    
    if address_confirmed is True:
        logger.info(f"[{conversation_id}] Router → diagnostics (address confirmed)")
        return "diagnostics"
    
    elif address_confirmed is False:
        logger.info(f"[{conversation_id}] Router → address_search (address rejected)")
        return "address_search"
    
    else:
        logger.info(f"[{conversation_id}] Router → end (waiting for user)")
        return "end"