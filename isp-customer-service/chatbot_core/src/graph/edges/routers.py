"""
Edge Routers
Conditional routing logic for workflow transitions
"""

from typing import Literal
from ..state import ConversationState
from .conditions import (
    is_customer_found,
    is_address_confirmed,
    is_provider_issue,
    is_authenticated,
    needs_authentication,
    is_problem_resolved,
    should_escalate,
    has_multiple_addresses,
    wants_more_help,
    is_conversation_ended
)
from langgraph.graph import END
import logging

logger = logging.getLogger(__name__)


# ========== NEW ROUTERS FOR CUSTOMER IDENTIFICATION ==========


def problem_capture_router(
    state: ConversationState
) -> Literal["phone_lookup_background", END]:
    """
    Route after problem capture node.
    
    Decision logic:
    - If waiting for user input (first run or clarification) → END (pause)
    - If problem identified → phone_lookup_background
    - Otherwise → END
    
    Args:
        state: Current state
        
    Returns:
        Next node name or END
    """
    logger.info("PROBLEM_CAPTURE ROUTER CALLED")
    logger.info(f"  waiting_for_user_input: {state.get('waiting_for_user_input')}")
    logger.info(f"  problem_identified: {state.get('problem_identified')}")
    
    # If waiting for user input, pause
    if state.get("waiting_for_user_input"):
        logger.info("  DECISION: END (waiting for input)")
        return END
    
    # If problem identified, proceed to phone lookup
    if state.get("problem_identified"):
        logger.info("  DECISION: phone_lookup_background")
        return "phone_lookup_background"
    
    # Otherwise, pause
    logger.info("  DECISION: END (no problem identified)")
    return END


def customer_identification_router(
    state: ConversationState
) -> Literal["address_confirmation", "address_selection", "address_search"]:
    """
    Route based on phone_info availability.
    
    Logic:
    - phone_info found + 1 address → address_confirmation
    - phone_info found + multiple addresses → address_selection
    - phone_info not found or no addresses → address_search
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    """
    logger.info("CUSTOMER_IDENTIFICATION ROUTER CALLED")
    
    phone_info = state.get("phone_info", {})
    
    logger.info(f"  phone_info.lookup_performed: {phone_info.get('lookup_performed')}")
    logger.info(f"  phone_info.found: {phone_info.get('found')}")
    
    if not phone_info.get("lookup_performed"):
        # Phone lookup not done yet (shouldn't happen in normal flow)
        logger.warning("  Phone lookup not performed!")
        logger.info("  DECISION: address_search")
        return "address_search"
    
    if not phone_info.get("found"):
        # No phone data found
        logger.info("  DECISION: address_search (phone not found)")
        return "address_search"
    
    matches = phone_info.get("possible_matches", [])
    
    if len(matches) == 0:
        logger.info("  DECISION: address_search (no matches)")
        return "address_search"
    
    # Get first match (assuming 1 customer per phone)
    match = matches[0]
    addresses = match.get("addresses", [])
    
    logger.info(f"  Found {len(addresses)} address(es)")
    
    if len(addresses) == 1:
        logger.info("  DECISION: address_confirmation (1 address)")
        return "address_confirmation"
    elif len(addresses) > 1:
        logger.info("  DECISION: address_selection (multiple addresses)")
        return "address_selection"
    else:
        logger.info("  DECISION: address_search (no addresses)")
        return "address_search"


def address_confirmation_router(
    state: ConversationState
) -> Literal["diagnostics", "address_search"]:
    """
    Route after address confirmation.
    
    Decision logic:
    - If address confirmed (user said YES) → diagnostics
    - If address not confirmed (user said NO) → address_search
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    """
    logger.info("ADDRESS_CONFIRMATION ROUTER CALLED")
    logger.info(f"  address_confirmed: {state.get('address_confirmed')}")
    
    if state.get("address_confirmed"):
        logger.info("  DECISION: diagnostics (address confirmed)")
        return "diagnostics"
    else:
        logger.info("  DECISION: address_search (user rejected address)")
        return "address_search"


def address_search_router(
    state: ConversationState
) -> Literal["diagnostics", "closing"]:
    """
    Route after address search.
    
    Decision logic:
    - If address search successful (found customer) → diagnostics
    - If not found → closing (cannot help)
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    """
    logger.info("ADDRESS_SEARCH ROUTER CALLED")
    logger.info(f"  address_search_successful: {state.get('address_search_successful')}")
    
    if state.get("address_search_successful"):
        logger.info("  DECISION: diagnostics (found by address)")
        return "diagnostics"
    else:
        logger.info("  DECISION: closing (address not found)")
        return "closing"


# ========== EXISTING ROUTERS ==========


def diagnostics_router(
    state: ConversationState
) -> Literal["inform_provider_issue", "troubleshooting", "closing"]:
    """
    Route after network diagnostics.
    
    Decision logic:
    - If provider issue → inform_provider_issue
    - If client side issue → troubleshooting (TODO)
    - If unclear/error → closing
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    """
    logger.info("DIAGNOSTICS ROUTER CALLED")
    
    if is_provider_issue(state):
        # Provider-side problem detected
        logger.info("  DECISION: inform_provider_issue")
        return "inform_provider_issue"
    else:
        # Client-side issue
        # TODO: Add troubleshooting nodes
        logger.info("  DECISION: closing (client-side, no troubleshooting yet)")
        return "closing"


def troubleshooting_router(
    state: ConversationState
) -> Literal["connection_test", "closing"]:
    """
    Route after troubleshooting step.
    
    Decision logic:
    - After each troubleshooting action → connection_test
    - If error → closing
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    
    Note: This router will be used later when troubleshooting nodes are added
    """
    # After troubleshooting action, always test connection
    return "connection_test"


def solution_evaluation_router(
    state: ConversationState
) -> Literal["closing", "troubleshooting", "ticket_creation"]:
    """
    Route after connection test / solution evaluation.
    
    Decision logic:
    - If resolved → closing
    - If partially resolved + retries left → troubleshooting (retry)
    - If not resolved + max retries → ticket_creation
    
    Args:
        state: Current state
        
    Returns:
        Next node name
    
    Note: This router will be used later when troubleshooting is implemented
    """
    if is_problem_resolved(state):
        # Problem solved!
        return "closing"
    
    elif should_escalate(state):
        # Tried enough times, escalate to ticket
        return "ticket_creation"
    
    else:
        # Try another solution
        return "troubleshooting"


def closing_router(
    state: ConversationState
) -> Literal["problem_capture", "__end__"]:
    """
    Route from closing node.
    
    Decision logic:
    - If user wants more help → restart (problem_capture)
    - If conversation ended → END
    
    Args:
        state: Current state
        
    Returns:
        Next node name or END
    """
    logger.info("CLOSING ROUTER CALLED")
    
    if wants_more_help(state):
        # User has another issue - loop back
        logger.info("  DECISION: problem_capture (more help needed)")
        return "problem_capture"
    else:
        # Really ending
        logger.info("  DECISION: __end__ (conversation done)")
        return "__end__"


# ========== ROUTER MAPPING FOR WORKFLOW ==========

ROUTER_MAP = {
    "problem_capture_router": problem_capture_router,
    "customer_identification_router": customer_identification_router,
    "address_confirmation_router": address_confirmation_router,
    "address_search_router": address_search_router,
    "diagnostics_router": diagnostics_router,
    "troubleshooting_router": troubleshooting_router,
    "solution_evaluation_router": solution_evaluation_router,
    "closing_router": closing_router,
}


def get_router(router_name: str):
    """
    Get router function by name.
    
    Args:
        router_name: Name of router
        
    Returns:
        Router function
        
    Raises:
        ValueError: If router not found
    """
    if router_name not in ROUTER_MAP:
        raise ValueError(f"Unknown router: {router_name}")
    
    return ROUTER_MAP[router_name]