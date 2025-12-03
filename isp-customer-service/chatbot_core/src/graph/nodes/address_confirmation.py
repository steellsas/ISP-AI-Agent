# # """
# # Address Confirmation Node
# # Confirms if the problem is at the suggested address from phone_info
# # """

# # from typing import Dict, Any
# # import logging
# # from ..state import ConversationState, add_message, get_last_user_message, set_confirmed_customer
# # from ...services.llm_service import get_llm_service

# # logger = logging.getLogger(__name__)


# # async def address_confirmation_node_async(state: ConversationState) -> Dict[str, Any]:
# #     """
# #     Confirm address from phone_info.
    
# #     Flow:
# #     1. First call: Ask "Ar problema adresu X?"
# #     2. Wait for user response
# #     3. Parse response (yes/no)
# #     4. If YES: Set customer_id + confirmed_address_id
# #     5. If NO: Go to address_search
    
# #     Args:
# #         state: Current conversation state
        
# #     Returns:
# #         Updated state with confirmation result
# #     """
    
# #     logger.info("=== ADDRESS CONFIRMATION ===")
    
# #     # KEY FIX: Check if we already asked the question
# #     # Use last_question to determine if this is first or second call
# #     already_asked = state.get("last_question") == "address_confirmation"
    
# #     if not already_asked:
# #         # FIRST CALL: Ask for confirmation
# #         logger.info("First call - asking for address confirmation")
        
# #         # Get address from phone_info
# #         phone_info = state.get("phone_info", {})
        
# #         if not phone_info.get("found"):
# #             logger.error("No phone_info available for address confirmation!")
# #             return {
# #                 "address_confirmed": False,
# #                 "waiting_for_user_input": False,
# #                 "current_node": "address_confirmation"
# #             }
        
# #         matches = phone_info.get("possible_matches", [])
# #         if not matches:
# #             logger.error("No matches in phone_info!")
# #             return {
# #                 "address_confirmed": False,
# #                 "waiting_for_user_input": False,
# #                 "current_node": "address_confirmation"
# #             }
        
# #         match = matches[0]
# #         addresses = match.get("addresses", [])
        
# #         if not addresses:
# #             logger.error("No addresses in match!")
# #             return {
# #                 "address_confirmed": False,
# #                 "waiting_for_user_input": False,
# #                 "current_node": "address_confirmation"
# #             }
        
# #         # Get first address
# #         address = addresses[0]
# #         full_address = address.get("full_address", "")
        
# #         # Build confirmation question
# #         question = f"Ar problema yra adresu {full_address}?"
        
# #         logger.info(f"Asking: {question}")
        
# #         # Add message
# #         state = add_message(
# #             state=state,
# #             role="assistant",
# #             content=question,
# #             node="address_confirmation"
# #         )
        
# #         return {
# #             "messages": state["messages"],
# #             "waiting_for_user_input": True,
# #             "last_question": "address_confirmation",
# #             "current_node": "address_confirmation"
# #         }
    
# #     # SECOND CALL: Process user response
# #     logger.info("Processing user response")
    
# #     user_response = get_last_user_message(state)
    
# #     if not user_response:
# #         logger.error("No user response found!")
# #         return {
# #             "address_confirmed": False,
# #             "waiting_for_user_input": False,
# #             "current_node": "address_confirmation"
# #         }
    
# #     logger.info(f"User said: {user_response}")
    
# #     # Use LLM to classify intent
# #     llm = get_llm_service()
    
# #     classification_prompt = f"""
# # Klasifikuok vartotojo atsakymą į "taip" arba "ne".

# # Vartotojas atsakė: "{user_response}"

# # Atsakyk vienu žodžiu: "taip" arba "ne"
# # """
    
# #     intent = await llm.generate(
# #         system_prompt="Tu esi klasifikatorius. Atsakyk tik 'taip' arba 'ne'.",
# #         messages=[{"role": "user", "content": classification_prompt}],
# #         temperature=0.0,
# #         max_tokens=10
# #     )
    
# #     intent_clean = intent.strip().lower()
# #     logger.info(f"Classified intent: {intent_clean}")
    
# #     if intent_clean in ["taip", "yes", "tak"]:
# #         # ✅ USER CONFIRMED
# #         logger.info("✅ Address CONFIRMED")
        
# #         # Get customer and address IDs from phone_info
# #         phone_info = state["phone_info"]
# #         match = phone_info["possible_matches"][0]
# #         address = match["addresses"][0]
        
# #         customer_id = match["customer_id"]
# #         address_id = address.get("address_id")
        
# #         logger.info(f"Setting customer_id={customer_id}, address_id={address_id}")
        
# #         # Set confirmed customer
# #         state = set_confirmed_customer(
# #             state=state,
# #             customer_id=customer_id,
# #             address_id=address_id
# #         )
        
# #         # Add acknowledgment message
# #         ack_message = "Supratau, patikrinsiu jūsų interneto ryšį."
# #         state = add_message(
# #             state=state,
# #             role="assistant",
# #             content=ack_message,
# #             node="address_confirmation"
# #         )
        
# #         return {
# #             "customer_id": customer_id,
# #             "confirmed_address_id": address_id,
# #             "customer_identified": True,
# #             "address_confirmed": True,
# #             "messages": state["messages"],
# #             "waiting_for_user_input": False,
# #             "last_question": None,  # ← Clear question
# #             "current_node": "address_confirmation"
# #         }
    
# #     else:
# #         # ❌ USER REJECTED
# #         logger.info("❌ Address NOT confirmed")
        
# #         # Add message
# #         msg = "Supratau. Galite pasakyti kitą adresą kuriuo problema?"
# #         state = add_message(
# #             state=state,
# #             role="assistant",
# #             content=msg,
# #             node="address_confirmation"
# #         )
        
# #         return {
# #             "address_confirmed": False,
# #             "messages": state["messages"],
# #             "waiting_for_user_input": False,
# #             "last_question": None,  # ← Clear question
# #             "current_node": "address_confirmation"
# #         }

# """
# Address Confirmation Node - Confirm customer's address with LLM
# """

# import sys
# import logging
# from pathlib import Path
# from pydantic import BaseModel
# from typing import Literal

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

# from src.services.llm import llm_json_completion
# from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

# logger = get_logger(__name__)


# # === Structured Output Schema ===

# class AddressConfirmationAnalysis(BaseModel):
#     """LLM response schema for address confirmation."""
#     confirmed: bool = False
#     rejected: bool = False
#     correction_provided: str | None = None  # Jei klientas pasakė kitą adresą
#     clarification_needed: bool = False
#     response_message: str  # Ką atsakyti klientui


# # === Prompts ===

# SYSTEM_PROMPT = """Tu esi ISP klientų aptarnavimo asistentas.
# Klientas turi patvirtinti savo adresą.

# Siūlomas adresas: {address}

# Analizuok kliento atsakymą ir nuspręsk:
# 1. Ar klientas PATVIRTINO adresą? (taip, jo, teisingai, tas pats, etc.)
# 2. Ar klientas ATMETĖ adresą? (ne, neteisingas, kitas adresas, etc.)
# 3. Ar klientas pateikė KITĄ adresą/korekciją?
# 4. Ar reikia patikslinti?

# Atsakyk JSON formatu:
# {{
#     "confirmed": true | false,
#     "rejected": true | false,
#     "correction_provided": "naujas adresas arba null",
#     "clarification_needed": true | false,
#     "response_message": "atsakymas klientui lietuviškai"
# }}

# Pavyzdžiai:
# - "taip" → confirmed=true, response_message="Puiku, adresas patvirtintas. Tikrinu jūsų ryšio būklę..."
# - "jo, teisingai" → confirmed=true
# - "ne, aš gyvenu Vilniuje" → rejected=true, correction_provided="Vilnius"
# - "tas pats, bet butas 7" → rejected=true, correction_provided="butas 7"
# - "hmm nežinau" → clarification_needed=true, response_message="Ar tikrai jūsų adresas yra {address}?"

# Būk draugiškas ir profesionalus."""


# def _get_address_string(state) -> str:
#     """Get formatted address from state."""
#     addresses = _get_attr(state, "customer_addresses", [])
#     if addresses:
#         addr = addresses[0]
#         return addr.get("full_address", f"{addr.get('city')}, {addr.get('street')} {addr.get('house_number')}")
#     return "nežinomas adresas"


# def _needs_confirmation_question(state) -> bool:
#     """Check if we need to ask confirmation question (no user response yet)."""
#     messages = _get_messages(state)
    
#     # Find last assistant message from this node
#     for msg in reversed(messages):
#         if msg.get("node") == "address_confirmation" and msg["role"] == "assistant":
#             # Check if there's a user message after it
#             idx = messages.index(msg)
#             for later_msg in messages[idx+1:]:
#                 if later_msg["role"] == "user":
#                     return False  # User already responded
#             return True  # No user response yet
    
#     return True  # No question asked yet


# def address_confirmation_node(state) -> dict:
#     """
#     Address confirmation node - asks and verifies address.
    
#     Flow:
#     1. First call: Ask confirmation question
#     2. Second call: Analyze user response
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         State update dict
#     """
#     logger.info("=== Address Confirmation Node ===")
    
#     address = _get_address_string(state)
#     customer_name = _get_attr(state, "customer_name", "")
    
#     # Check if we need to ask the question
#     if _needs_confirmation_question(state):
#         logger.info(f"Asking confirmation for address: {address}")
        
#         question = f"Ačiū, {customer_name.split()[0] if customer_name else 'kliente'}. Ar jūsų adresas yra {address}?"
        
#         message = add_message(
#             role="assistant",
#             content=question,
#             node="address_confirmation"
#         )
        
#         return {
#             "messages": [message],
#             "current_node": "address_confirmation",
#         }
    
#     # Analyze user response
#     user_message = get_last_user_message(state)
#     logger.info(f"Analyzing user response: {user_message}")
    
#     # Build prompt with address context
#     system_prompt = SYSTEM_PROMPT.format(address=address)
    
#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user", "content": user_message}
#     ]
    
#     try:
#         response = llm_json_completion(
#             messages=messages,
#             temperature=0.2,
#             max_tokens=200
#         )
        
#         analysis = AddressConfirmationAnalysis(**response)
#         logger.info(f"Analysis: confirmed={analysis.confirmed}, rejected={analysis.rejected}")
        
#     except Exception as e:
#         logger.error(f"LLM error: {e}")
#         # Fallback - ask again
#         fallback_message = add_message(
#             role="assistant",
#             content=f"Atsiprašau, ar galėtumėte patvirtinti - jūsų adresas yra {address}?",
#             node="address_confirmation"
#         )
#         return {
#             "messages": [fallback_message],
#             "current_node": "address_confirmation",
#             "last_error": str(e)
#         }
    
#     # Create response message
#     message = add_message(
#         role="assistant",
#         content=analysis.response_message,
#         node="address_confirmation"
#     )
    
#     # Update state based on analysis
#     if analysis.confirmed:
#         addresses = _get_attr(state, "customer_addresses", [])
#         confirmed_addr = addresses[0] if addresses else {}
        
#         return {
#             "messages": [message],
#             "current_node": "address_confirmation",
#             "address_confirmed": True,
#             "confirmed_address_id": confirmed_addr.get("address_id"),
#             "confirmed_address": address,
#         }
    
#     elif analysis.rejected:
#         # Don't add message - address_search will ask for address
#         return {
#             "messages": [],  
#             "current_node": "address_confirmation",
#             "address_confirmed": False,
#             "address_correction": analysis.correction_provided,
#         }
    
#     else:
#         # Need clarification - will loop back
#         return {
#             "messages": [message],
#             "current_node": "address_confirmation",
#         }


# def address_confirmation_router(state) -> str:
#     """
#     Route after address confirmation.
    
#     Returns:
#         - "end" → wait for user input
#         - "diagnostics" → address confirmed
#         - "address_search" → address rejected
#     """
#     address_confirmed = _get_attr(state, "address_confirmed")
    
#     if address_confirmed is True:
#         logger.info("Address confirmed → diagnostics")
#         return "diagnostics"
    
#     elif address_confirmed is False:
#         logger.info("Address rejected → address_search")
#         return "address_search"
    
#     else:
#         # Just asked question OR need clarification → wait for user
#         logger.info("Waiting for user response → end")
#         return "end"


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


# =============================================================================
# STRUCTURED OUTPUT SCHEMA
# =============================================================================

class AddressConfirmationAnalysis(BaseModel):
    """LLM response schema for address confirmation."""
    confirmed: bool = False
    rejected: bool = False
    correction_provided: str | None = None  # If customer provided different address
    clarification_needed: bool = False
    response_message: str  # What to respond to customer


# =============================================================================
# PROMPT BUILDER
# =============================================================================

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
    
    # Find last assistant message from this node
    for msg in reversed(messages):
        if msg.get("node") == "address_confirmation" and msg["role"] == "assistant":
            # Check if there's a user message after it
            idx = messages.index(msg)
            for later_msg in messages[idx+1:]:
                if later_msg["role"] == "user":
                    return False  # User already responded
            return True  # No user response yet
    
    return True  # No question asked yet


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
        # Check if we need to ask the question
        if _needs_confirmation_question(state):
            logger.info(f"[{conversation_id}] Asking confirmation for address: {address}")
            
            # Build question using translation
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
        
        # Build prompt and call LLM
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
        # Just asked question OR need clarification → wait for user
        logger.info(f"[{conversation_id}] Router → end (waiting for user)")
        return "end"