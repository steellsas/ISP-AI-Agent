"""
Address Search Node - Find customer by address when phone lookup fails
"""

import sys
import logging
from pathlib import Path
from pydantic import BaseModel

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

from src.services.llm import llm_json_completion
from src.services.crm import get_customer_by_address
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = get_logger(__name__)


# === Structured Output Schema ===

class AddressExtraction(BaseModel):
    """LLM response schema for address extraction."""
    has_address: bool = False
    city: str | None = None
    street: str | None = None
    house_number: str | None = None
    apartment_number: str | None = None
    clarification_question: str | None = None  # Jei trūksta info


# === Prompts ===

SYSTEM_PROMPT = """Tu esi ISP klientų aptarnavimo asistentas.
Klientas nerastas pagal telefono numerį. Tau reikia išgauti jo adresą.

Analizuok kliento žinutę ir ištrauk adreso komponentus:
- city: miestas (pvz. "Šiauliai", "Vilnius")
- street: gatvė (pvz. "Tilžės g.", "Vytauto g.")
- house_number: namo numeris (pvz. "12", "45A")
- apartment_number: buto numeris (pvz. "5", "23") - gali būti null

Atsakyk JSON formatu:
{
    "has_address": true | false,
    "city": "miestas arba null",
    "street": "gatvė arba null",
    "house_number": "namo nr arba null",
    "apartment_number": "buto nr arba null",
    "clarification_question": "klausimas jei trūksta info, arba null"
}

Jei klientas nepateikė pilno adreso, užduok klausimą.

Pavyzdžiai:
- "Gyvenu Šiauliuose, Tilžės 12-5" → has_address=true, city="Šiauliai", street="Tilžės g.", house_number="12", apartment_number="5"
- "Vilnius, Gedimino 1" → has_address=true, city="Vilnius", street="Gedimino pr.", house_number="1", apartment_number=null
- "Šiauliuose gyvenu" → has_address=false, clarification_question="Kokia jūsų gatvė ir namo numeris?"
- "Tilžės 15" → has_address=false, clarification_question="Kokiame mieste gyvenate?"

Būk draugiškas."""


ASK_ADDRESS_PROMPT = "Deja, nepavyko jūsų rasti pagal telefono numerį. Ar galėtumėte pasakyti savo adresą (miestas, gatvė, namo numeris)?"


def _needs_address_question(state) -> bool:
    """Check if we need to ask for address (first time in this node)."""
    messages = _get_messages(state)
    
    # Check if we already asked for address
    for msg in reversed(messages):
        if msg.get("node") == "address_search" and msg["role"] == "assistant":
            # Check if there's a user message after
            idx = messages.index(msg)
            for later_msg in messages[idx+1:]:
                if later_msg["role"] == "user":
                    return False
            return True
    
    return True


def address_search_node(state) -> dict:
    """
    Address search node - asks for and extracts address.
    
    Flow:
    1. First call: Ask for address
    2. Subsequent calls: Extract address from user response
    3. If complete: Lookup in CRM
    4. If incomplete: Ask clarification
    
    Args:
        state: Current conversation state
        
    Returns:
        State update dict
    """
    logger.info("=== Address Search Node ===")
    
    # Check if we need to ask the initial question
    if _needs_address_question(state):
        logger.info("Asking for address")
        
        message = add_message(
            role="assistant",
            content=ASK_ADDRESS_PROMPT,
            node="address_search"
        )
        
        return {
            "messages": [message],
            "current_node": "address_search",
        }
    
    # Extract address from user message
    user_message = get_last_user_message(state)
    logger.info(f"Extracting address from: {user_message}")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = llm_json_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=200
        )
        
        extraction = AddressExtraction(**response)
        logger.info(f"Extraction: has_address={extraction.has_address}, city={extraction.city}, street={extraction.street}")
        
    except Exception as e:
        logger.error(f"LLM error: {e}")
        fallback_message = add_message(
            role="assistant",
            content="Atsiprašau, ar galėtumėte pakartoti savo adresą?",
            node="address_search"
        )
        return {
            "messages": [fallback_message],
            "current_node": "address_search",
            "last_error": str(e)
        }
    
    # If address incomplete, ask clarification
    if not extraction.has_address or not all([extraction.city, extraction.street, extraction.house_number]):
        question = extraction.clarification_question or "Ar galėtumėte patikslinti savo adresą (miestas, gatvė, namo numeris)?"
        
        message = add_message(
            role="assistant",
            content=question,
            node="address_search"
        )
        
        return {
            "messages": [message],
            "current_node": "address_search",
        }
    
    # Address complete - lookup in CRM
    logger.info(f"Looking up address: {extraction.city}, {extraction.street} {extraction.house_number}")
    
    result = get_customer_by_address(
        city=extraction.city,
        street=extraction.street,
        house_number=extraction.house_number,
        apartment_number=extraction.apartment_number
    )
    
    if result.get("success"):
        customer = result["customer"]
        address = customer.get("address", {})
        
        logger.info(f"Found customer: {customer['customer_id']}")
        
        confirm_message = add_message(
            role="assistant",
            content=f"Radau jus sistemoje! {customer['first_name']} {customer['last_name']}, adresas: {address.get('full_address', extraction.city + ', ' + extraction.street + ' ' + extraction.house_number)}. Tikrinu jūsų ryšio būklę...",
            node="address_search"
        )
        
        return {
            "messages": [confirm_message],
            "current_node": "address_search",
            "customer_id": customer["customer_id"],
            "customer_name": f"{customer['first_name']} {customer['last_name']}",
            "customer_addresses": [address],
            "address_confirmed": True,
            "confirmed_address_id": address.get("address_id"),
            "confirmed_address": address.get("full_address"),
            "address_search_successful": True,
        }
    
    else:
        # Customer not found by address
        logger.warning(f"Customer not found by address: {result.get('message')}")
        
        not_found_message = add_message(
            role="assistant",
            content=f"Atsiprašau, bet adresu {extraction.city}, {extraction.street} {extraction.house_number} kliento neradome. Galbūt galite patikrinti adresą arba susisiekti su mumis kitu būdu.",
            node="address_search"
        )
        
        return {
            "messages": [not_found_message],
            "current_node": "address_search",
            "address_search_successful": False,
            "conversation_ended": True,
        }


def address_search_router(state) -> str:
    """
    Route after address search.
    
    Returns:
        - "end" → wait for user input
        - "diagnostics" → customer found
        - "closing" → customer not found, end conversation
    """
    address_search_successful = _get_attr(state, "address_search_successful")
    conversation_ended = _get_attr(state, "conversation_ended", False)
    
    if conversation_ended:
        logger.info("Conversation ended → closing")
        return "closing"
    
    if address_search_successful is True:
        logger.info("Customer found by address → diagnostics")
        return "diagnostics"
    
    # Still searching
    logger.info("Waiting for address → end")
    return "end"

# """
# Address Search Node
# Asks user for address and looks up customer in CRM
# """

# from typing import Dict, Any
# import logging
# import json
# from ..state import ConversationState, add_message, get_last_user_message, set_confirmed_customer, add_tool_call, add_error
# from ...services.llm_service import get_llm_service
# from ...services.mcp_service import get_mcp_service

# logger = logging.getLogger(__name__)


# async def address_search_node_async(state: ConversationState) -> Dict[str, Any]:
#     """
#     Ask for address and search customer.
    
#     Flow:
#     1. First call: Ask "Kokiu adresu problema?"
#     2. Wait for user response
#     3. Parse address with LLM (extract city, street, house)
#     4. Call lookup_customer_by_address
#     5. If found: Set customer_id + confirmed_address_id
#     6. If not found: Cannot help
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         Updated state with search result
#     """
    
#     logger.info("=== ADDRESS SEARCH ===")
    
#     # Check if this is first call or response processing
#     if not state.get("waiting_for_user_input") or not state.get("address_search_asked"):
#         # FIRST CALL: Ask for address
#         logger.info("First call - asking for address")
        
#         question = "Galite pasakyti adresą kuriuo problema? (pvz., Tilžės 60, Šiauliai)"
        
#         state = add_message(
#             state=state,
#             role="assistant",
#             content=question,
#             node="address_search"
#         )
        
#         return {
#             "messages": state["messages"],
#             "waiting_for_user_input": True,
#             "last_question": "address_search",
#             "address_search_asked": True,
#             "current_node": "address_search"
#         }
    
#     # SECOND CALL: Parse address and search
#     logger.info("Processing address input")
    
#     user_response = get_last_user_message(state)
#     logger.info(f"User provided address: {user_response}")
    
#     # Use LLM to extract address components
#     llm = get_llm_service()
    
#     extract_prompt = f"""
# Išgauk adreso komponentus iš teksto.

# Tekstas: "{user_response}"

# Grąžink JSON formatą:
# {{
#     "city": "miestas",
#     "street": "gatvė",
#     "house_number": "namo numeris",
#     "apartment_number": "buto numeris arba null"
# }}

# Pavyzdys:
# Tekstas: "Tilžės 60, Šiauliai"
# Atsakymas: {{"city": "Šiauliai", "street": "Tilžės", "house_number": "60", "apartment_number": null}}
# """
    
#     try:
#         address_json = await llm.generate(
#             system_prompt="Tu esi adresų išgavimo asistentas. Grąžink tik JSON.",
#             messages=[{"role": "user", "content": extract_prompt}],
#             temperature=0.0,
#             max_tokens=200
#         )
        
#         logger.info(f"LLM extracted: {address_json}")
        
#         # Parse JSON
#         # Remove markdown if present
#         address_json_clean = address_json.strip()
#         if address_json_clean.startswith("```json"):
#             address_json_clean = address_json_clean.replace("```json", "").replace("```", "").strip()
        
#         address_data = json.loads(address_json_clean)
        
#         logger.info(f"Parsed address: {address_data}")
        
#     except Exception as e:
#         logger.error(f"Failed to parse address: {e}")
        
#         # Fallback: simple split
#         parts = user_response.split(",")
#         address_data = {
#             "city": parts[-1].strip() if len(parts) > 1 else "Šiauliai",
#             "street": parts[0].split()[0] if parts else "",
#             "house_number": parts[0].split()[1] if len(parts[0].split()) > 1 else "",
#             "apartment_number": None
#         }
        
#         logger.info(f"Fallback parsed: {address_data}")
    
#     # Call MCP lookup_customer_by_address
#     mcp = get_mcp_service()
    
#     try:
#         lookup_args = {
#             "city": address_data.get("city", ""),
#             "street": address_data.get("street", ""),
#             "house_number": address_data.get("house_number", "")
#         }
        
#         if address_data.get("apartment_number"):
#             lookup_args["apartment_number"] = address_data["apartment_number"]
        
#         logger.info(f"Calling lookup_customer_by_address with: {lookup_args}")
        
#         result = await mcp.call_tool(
#             server_name="crm_service",
#             tool_name="lookup_customer_by_address",
#             arguments=lookup_args
#         )
        
#         logger.info(f"MCP result: {result}")
        
#         # Record tool call
#         state = add_tool_call(
#             state=state,
#             tool_name="lookup_customer_by_address",
#             tool_input=lookup_args,
#             tool_output=result,
#             node="address_search"
#         )
        
#         # Check if found
#         if result and result.get("success") and result.get("found"):
#             # ✅ FOUND
#             logger.info("✅ Customer found by address")
            
#             customer_info = result.get("customer", {})
#             addresses = result.get("addresses", [])
            
#             if not addresses:
#                 logger.error("Customer found but no addresses!")
#                 raise Exception("No addresses in result")
            
#             address = addresses[0]
            
#             customer_id = customer_info.get("customer_id")
#             address_id = address.get("address_id")
            
#             logger.info(f"Setting customer_id={customer_id}, address_id={address_id}")
            
#             # Set confirmed customer
#             state = set_confirmed_customer(
#                 state=state,
#                 customer_id=customer_id,
#                 address_id=address_id
#             )
            
#             # Add acknowledgment
#             ack_message = f"Radau! Patikrinsiu ryšį adresu {address.get('full_address')}."
#             state = add_message(
#                 state=state,
#                 role="assistant",
#                 content=ack_message,
#                 node="address_search"
#             )
            
#             return {
#                 "customer_id": customer_id,
#                 "confirmed_address_id": address_id,
#                 "customer_identified": True,
#                 "address_search_successful": True,
#                 "messages": state["messages"],
#                 "tool_calls": state["tool_calls"],
#                 "waiting_for_user_input": False,
#                 "current_node": "address_search"
#             }
        
#         else:
#             # ❌ NOT FOUND
#             logger.info("❌ Customer not found by address")
            
#             msg = "Deja, nepavyko rasti šio adreso mūsų sistemoje. Galbūt galite pabandyti kitaip suformuluoti adresą?"
#             state = add_message(
#                 state=state,
#                 role="assistant",
#                 content=msg,
#                 node="address_search"
#             )
            
#             return {
#                 "address_search_successful": False,
#                 "messages": state["messages"],
#                 "tool_calls": state["tool_calls"],
#                 "waiting_for_user_input": False,
#                 "current_node": "address_search"
#             }
    
#     except Exception as e:
#         # Handle error
#         logger.error(f"Address search failed: {e}", exc_info=True)
        
#         state = add_error(
#             state=state,
#             error_message=f"Address search failed: {str(e)}",
#             node="address_search",
#             error_type="mcp_tool_error"
#         )
        
#         msg = "Atsiprašau, įvyko klaida ieškant adreso. Bandykite dar kartą."
#         state = add_message(
#             state=state,
#             role="assistant",
#             content=msg,
#             node="address_search"
#         )
        
#         return {
#             "address_search_successful": False,
#             "messages": state["messages"],
#             "errors": state["errors"],
#             "last_error": state["last_error"],
#             "waiting_for_user_input": False,
#             "current_node": "address_search"
#         }

