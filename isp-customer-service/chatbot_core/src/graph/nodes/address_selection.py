"""
Address Selection Node
Let user pick from multiple addresses when phone lookup finds multiple
"""

from typing import Dict, Any
import logging
from ..state import ConversationState, add_message, get_last_user_message, set_confirmed_customer
from ...services.llm_service import get_llm_service

logger = logging.getLogger(__name__)


async def address_selection_node_async(state: ConversationState) -> Dict[str, Any]:
    """
    Let user select from multiple addresses.

    Flow:
    1. First call: Show numbered list of addresses
    2. Wait for user selection
    3. Parse selection (number or text match)
    4. Set customer_id + confirmed_address_id

    Args:
        state: Current conversation state

    Returns:
        Updated state with selected address
    """

    logger.info("=== ADDRESS SELECTION ===")

    if not state.get("waiting_for_user_input"):
        # FIRST CALL: Show address list
        logger.info("First call - showing address options")

        # Get addresses from phone_info
        phone_info = state.get("phone_info", {})

        if not phone_info.get("found"):
            logger.error("No phone_info available!")
            return {
                "address_confirmed": False,
                "waiting_for_user_input": False,
                "current_node": "address_selection",
            }

        matches = phone_info.get("possible_matches", [])
        if not matches:
            logger.error("No matches in phone_info!")
            return {
                "address_confirmed": False,
                "waiting_for_user_input": False,
                "current_node": "address_selection",
            }

        match = matches[0]
        addresses = match.get("addresses", [])

        if len(addresses) <= 1:
            logger.error("Address selection called but only 1 address!")
            return {
                "address_confirmed": False,
                "waiting_for_user_input": False,
                "current_node": "address_selection",
            }

        # Build numbered list
        options_text = "\n".join(
            [f"{i+1}. {addr.get('full_address', 'Unknown')}" for i, addr in enumerate(addresses)]
        )

        question = f"Turime kelis jūsų adresus:\n{options_text}\n\nKuriuo adresu problema?"

        logger.info(f"Showing {len(addresses)} addresses")

        # Add message
        state = add_message(
            state=state, role="assistant", content=question, node="address_selection"
        )

        return {
            "messages": state["messages"],
            "waiting_for_user_input": True,
            "last_question": "address_selection",
            "current_node": "address_selection",
        }

    # SECOND CALL: Process selection
    logger.info("Processing user selection")

    user_response = get_last_user_message(state)
    logger.info(f"User selected: {user_response}")

    # Get addresses
    phone_info = state["phone_info"]
    match = phone_info["possible_matches"][0]
    addresses = match["addresses"]

    selected_address = None

    # Try to parse as number
    user_text = user_response.strip()

    if user_text.isdigit():
        idx = int(user_text) - 1
        if 0 <= idx < len(addresses):
            selected_address = addresses[idx]
            logger.info(f"Selected by number: {idx+1}")

    # If not a valid number, use LLM to match text
    if not selected_address:
        logger.info("Not a number, using LLM to match address")

        llm = get_llm_service()

        # Build prompt with all addresses
        addresses_list = "\n".join(
            [f"{i+1}. {addr.get('full_address')}" for i, addr in enumerate(addresses)]
        )

        match_prompt = f"""
Vartotojas pasirinko adresą: "{user_response}"

Galimi adresai:
{addresses_list}

Kuris numeris labiausiai atitinka vartotojo pasirinkimą?
Atsakyk tik numeriu (1, 2, 3, etc.)
"""

        match_result = await llm.generate(
            system_prompt="Tu esi adresų atitikimo klasifikatorius. Atsakyk tik numeriu.",
            messages=[{"role": "user", "content": match_prompt}],
            temperature=0.0,
            max_tokens=10,
        )

        match_num = match_result.strip()
        if match_num.isdigit():
            idx = int(match_num) - 1
            if 0 <= idx < len(addresses):
                selected_address = addresses[idx]
                logger.info(f"Selected by LLM match: {idx+1}")

    # Fallback to first address if still none
    if not selected_address:
        logger.warning("Could not determine selection, using first address")
        selected_address = addresses[0]

    # Set confirmed customer
    customer_id = match["customer_id"]
    address_id = selected_address.get("address_id")

    logger.info(f"Setting customer_id={customer_id}, address_id={address_id}")

    state = set_confirmed_customer(state=state, customer_id=customer_id, address_id=address_id)

    # Add acknowledgment
    ack_message = f"Supratau, patikrinsiu ryšį adresu {selected_address.get('full_address')}."
    state = add_message(
        state=state, role="assistant", content=ack_message, node="address_selection"
    )

    return {
        "customer_id": customer_id,
        "confirmed_address_id": address_id,
        "customer_identified": True,
        "address_confirmed": True,
        "messages": state["messages"],
        "waiting_for_user_input": False,
        "current_node": "address_selection",
    }
