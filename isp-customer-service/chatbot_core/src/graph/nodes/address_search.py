"""
Address Search Node - Find customer by address when phone lookup fails

Asks customer for address and looks up in CRM.
Uses LLM for address extraction from natural language.
Supports multiple languages via translation service.
"""

import logging
from typing import Any
from pydantic import BaseModel

from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr
from src.services.llm import llm_json_completion
from src.services.crm import get_customer_by_address
from src.services.language_service import get_language, get_language_name
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# STRUCTURED OUTPUT SCHEMA
# =============================================================================


class AddressExtraction(BaseModel):
    """LLM response schema for address extraction."""

    has_address: bool = False
    city: str | None = None
    street: str | None = None
    house_number: str | None = None
    apartment_number: str | None = None
    clarification_question: str | None = None  # If info is missing


# =============================================================================
# PROMPT BUILDER
# =============================================================================


def _build_extraction_prompt() -> str:
    """
    Build system prompt for address extraction.

    Prompt is in English, but instructs LLM to respond appropriately.

    Returns:
        System prompt string
    """
    output_language = get_language_name()

    return f"""You are an ISP customer service assistant.
The customer was not found by phone number. You need to extract their address.

Analyze the customer's message and extract address components:
- city: city name (e.g., "Vilnius", "Kaunas", "Šiauliai")
- street: street name (e.g., "Gedimino pr.", "Tilžės g.")
- house_number: house number (e.g., "12", "45A")
- apartment_number: apartment number (e.g., "5", "23") - can be null

Respond in JSON format:
{{
    "has_address": true | false,
    "city": "city or null",
    "street": "street or null",
    "house_number": "house number or null",
    "apartment_number": "apartment number or null",
    "clarification_question": "question if info missing, in {output_language}, or null"
}}

If customer didn't provide complete address, ask clarification question.

Examples:
- "I live in Šiauliai, Tilžės 12-5" → has_address=true, city="Šiauliai", street="Tilžės g.", house_number="12", apartment_number="5"
- "Vilnius, Gedimino 1" → has_address=true, city="Vilnius", street="Gedimino pr.", house_number="1", apartment_number=null
- "I live in Šiauliai" → has_address=false, clarification_question="What is your street and house number?"
- "Tilžės 15" → has_address=false, clarification_question="Which city do you live in?"

CRITICAL: clarification_question MUST be in {output_language} language.
Be friendly."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _needs_address_question(state: Any) -> bool:
    """Check if we need to ask for address (first time in this node)."""
    messages = _get_messages(state)

    # Check if we already asked for address
    for msg in reversed(messages):
        if msg.get("node") == "address_search" and msg["role"] == "assistant":
            # Check if there's a user message after
            idx = messages.index(msg)
            for later_msg in messages[idx + 1 :]:
                if later_msg["role"] == "user":
                    return False
            return True

    return True


# =============================================================================
# NODE FUNCTION
# =============================================================================


def address_search_node(state: Any) -> dict:
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
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Address search node started")

    try:
        # Check if we need to ask the initial question
        if _needs_address_question(state):
            logger.info(f"[{conversation_id}] Asking for address")

            message = add_message(
                role="assistant", content=t("address.ask_for_address"), node="address_search"
            )

            return {
                "messages": [message],
                "current_node": "address_search",
            }

        # Extract address from user message
        user_message = get_last_user_message(state)
        logger.info(f"[{conversation_id}] Extracting address from: {user_message[:50]}...")

        # Build prompt and call LLM
        system_prompt = _build_extraction_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        response = llm_json_completion(messages=messages, temperature=0.2, max_tokens=200)

        extraction = AddressExtraction(**response)

        logger.info(
            f"[{conversation_id}] Extraction result | "
            f"has_address={extraction.has_address} | "
            f"city={extraction.city} | "
            f"street={extraction.street}"
        )

        # If address incomplete, ask clarification
        if not extraction.has_address or not all(
            [extraction.city, extraction.street, extraction.house_number]
        ):
            question = extraction.clarification_question or t("address.clarify_address")

            message = add_message(role="assistant", content=question, node="address_search")

            logger.info(f"[{conversation_id}] Address incomplete, asking clarification")

            return {
                "messages": [message],
                "current_node": "address_search",
            }

        # Address complete - lookup in CRM
        logger.info(
            f"[{conversation_id}] Looking up address: "
            f"{extraction.city}, {extraction.street} {extraction.house_number}"
        )

        result = get_customer_by_address(
            city=extraction.city,
            street=extraction.street,
            house_number=extraction.house_number,
            apartment_number=extraction.apartment_number,
        )

        if result.get("success"):
            customer = result["customer"]
            address = customer.get("address", {})
            customer_name = f"{customer['first_name']} {customer['last_name']}"
            full_address = (
                address.get("full_address")
                or f"{extraction.city}, {extraction.street} {extraction.house_number}"
            )

            logger.info(
                f"[{conversation_id}] Customer found by address | "
                f"customer_id={customer['customer_id']} | "
                f"lang={get_language()}"
            )

            confirm_message = add_message(
                role="assistant",
                content=t("address.found", customer_name=customer_name, address=full_address),
                node="address_search",
            )

            return {
                "messages": [confirm_message],
                "current_node": "address_search",
                "customer_id": customer["customer_id"],
                "customer_name": customer_name,
                "customer_addresses": [address],
                "address_confirmed": True,
                "confirmed_address_id": address.get("address_id"),
                "confirmed_address": full_address,
                "address_search_successful": True,
            }

        else:
            # Customer not found by address
            full_address = f"{extraction.city}, {extraction.street} {extraction.house_number}"

            logger.warning(f"[{conversation_id}] Customer not found by address: {full_address}")

            not_found_message = add_message(
                role="assistant",
                content=t("address.not_found", address=full_address),
                node="address_search",
            )

            return {
                "messages": [not_found_message],
                "current_node": "address_search",
                "address_search_successful": False,
                "conversation_ended": True,
            }

    except Exception as e:
        logger.error(f"[{conversation_id}] Address search error: {e}", exc_info=True)

        fallback_message = add_message(
            role="assistant",
            content=t("errors.repeat_request", default="Ar galėtumėte pakartoti savo adresą?"),
            node="address_search",
        )

        return {
            "messages": [fallback_message],
            "current_node": "address_search",
            "last_error": str(e),
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================


def address_search_router(state: Any) -> str:
    """
    Route after address search.

    Returns:
        - "diagnostics" → customer found
        - "closing" → customer not found, end conversation
        - "end" → waiting for user input
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    address_search_successful = _get_attr(state, "address_search_successful")
    conversation_ended = _get_attr(state, "conversation_ended", False)

    if conversation_ended:
        logger.info(f"[{conversation_id}] Router → closing (conversation ended)")
        return "closing"

    if address_search_successful is True:
        logger.info(f"[{conversation_id}] Router → diagnostics (customer found)")
        return "diagnostics"

    # Still searching
    logger.info(f"[{conversation_id}] Router → end (waiting for address)")
    return "end"
