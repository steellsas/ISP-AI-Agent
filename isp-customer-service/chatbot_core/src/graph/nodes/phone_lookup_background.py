"""
Phone Lookup Background Node
Background customer lookup by phone number (informational only)
Does NOT set customer_id - only stores to phone_info
"""

from typing import Dict, Any
import logging
from ..state import ConversationState, add_tool_call, add_error
from ...services.mcp_service import get_mcp_service

logger = logging.getLogger(__name__)


async def phone_lookup_background_async(state: ConversationState) -> Dict[str, Any]:
    """
    Background phone lookup - informational only.
    
    This node:
    - Looks up customer by phone number
    - Stores results in phone_info (NOT customer)
    - Does NOT set customer_id
    - Runs in parallel with problem_capture
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with phone_info
    """
    
    logger.info("=== PHONE LOOKUP BACKGROUND ===")
    
    # Get phone number
    phone = state.get("phone_number") or state.get("customer", {}).get("phone")
    
    if not phone:
        logger.warning("No phone number available for lookup")
        return {
            "phone_info": {
                "lookup_performed": True,
                "found": False,
                "phone_number": None,
                "possible_matches": []
            },
            "current_node": "phone_lookup_background"
        }
    
    logger.info(f"Looking up phone: {phone}")
    
    # Get MCP service (singleton)
    mcp = get_mcp_service()
    
    try:
        # Call CRM tool via MCP
        customer_data = await mcp.call_tool(
            server_name="crm_service",
            tool_name="lookup_customer_by_phone",
            arguments={"phone_number": phone}
        )
        
        logger.info(f"MCP response: {customer_data}")
        
        # Record tool call
        state = add_tool_call(
            state=state,
            tool_name="lookup_customer_by_phone",
            tool_input={"phone_number": phone},
            tool_output=customer_data,
            node="phone_lookup_background"
        )
        
        # Check if customer found
        if customer_data and customer_data.get("success") and customer_data.get("found"):
            logger.info("✅ Customer found in background lookup")
            
            # Extract customer data
            customer_info = customer_data.get("customer", {})
            addresses = customer_data.get("addresses", [])
            
            # Build phone_info structure
            phone_info_result = {
                "lookup_performed": True,
                "found": True,
                "phone_number": phone,
                "possible_matches": [
                    {
                        "customer_id": customer_info.get("customer_id"),
                        "name": f"{customer_info.get('first_name', '')} {customer_info.get('last_name', '')}".strip(),
                        "first_name": customer_info.get("first_name"),
                        "last_name": customer_info.get("last_name"),
                        "addresses": addresses
                    }
                ]
            }
            
            logger.info(f"Phone info stored: {len(addresses)} address(es) found")
            
            return {
                "phone_info": phone_info_result,
                "tool_calls": state["tool_calls"],
                "current_node": "phone_lookup_background"
            }
        else:
            # Customer not found
            logger.info("❌ Customer not found in background lookup")
            
            return {
                "phone_info": {
                    "lookup_performed": True,
                    "found": False,
                    "phone_number": phone,
                    "possible_matches": []
                },
                "tool_calls": state["tool_calls"],
                "current_node": "phone_lookup_background"
            }
        
    except Exception as e:
        # Handle error
        logger.error(f"Phone lookup failed: {e}", exc_info=True)
        
        state = add_error(
            state=state,
            error_message=f"Phone lookup failed: {str(e)}",
            node="phone_lookup_background",
            error_type="mcp_tool_error"
        )
        
        return {
            "phone_info": {
                "lookup_performed": True,
                "found": False,
                "phone_number": phone,
                "possible_matches": []
            },
            "errors": state["errors"],
            "last_error": state["last_error"],
            "current_node": "phone_lookup_background"
        }

