# """
# Diagnostics Node
# Runs network diagnostics using MCP network diagnostic service
# """

# from typing import Dict, Any
# from ..state import ConversationState, add_tool_call, add_message, add_error
# from ...services.mcp_service import get_mcp_service


# async def diagnostics_node_async(state: ConversationState) -> Dict[str, Any]:
#     """
#     Run network diagnostics.
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         Updated state with diagnostic results
#     """
    
#     customer = state.get("customer", {})
#     customer_id = customer.get("customer_id")
#     address = customer.get("address", {})
    
#     if not customer_id:
#         return {
#             "diagnostics_completed": False,
#             "last_error": "No customer ID for diagnostics",
#             "current_node": "diagnostics"
#         }
    
#     # Get MCP service (singleton)
#     mcp = get_mcp_service()
    
#     # Inform user diagnostics starting
#     state = add_message(
#         state=state,
#         role="assistant",
#         content="Atlieku tinklo diagnostiką...",
#         node="diagnostics"
#     )
    
#     try:
#         # Call multiple diagnostic tools
#         # (Since run_diagnostics doesn't exist yet, we use existing tools)
        
#         # 1. Check port status
#         port_status = await mcp.call_tool(
#             server_name="network_diagnostic_service",
#             tool_name="check_port_status",
#             arguments={"customer_id": customer_id}
#         )
        
#         # 2. Check area outages
#         area_outages = await mcp.call_tool(
#             server_name="network_diagnostic_service",
#             tool_name="check_area_outages",
#             arguments={
#                 "city": address.get("city", ""),
#                 "street": address.get("street", "")
#             }
#         )
        
#         # 3. Check signal quality
#         signal_quality = await mcp.call_tool(
#             server_name="network_diagnostic_service",
#             tool_name="check_signal_quality",
#             arguments={"customer_id": customer_id}
#         )
        
#         # Aggregate results
#         diagnostic_results = {
#             "port_status": port_status,
#             "area_outages": area_outages,
#             "signal_quality": signal_quality,
#             "success": True
#         }
        
#         # Record tool calls
#         state = add_tool_call(
#             state=state,
#             tool_name="check_port_status",
#             tool_input={"customer_id": customer_id},
#             tool_output=port_status,
#             node="diagnostics"
#         )
        
#         state = add_tool_call(
#             state=state,
#             tool_name="check_area_outages",
#             tool_input={"city": address.get("city"), "street": address.get("street")},
#             tool_output=area_outages,
#             node="diagnostics"
#         )
        
#         state = add_tool_call(
#             state=state,
#             tool_name="check_signal_quality",
#             tool_input={"customer_id": customer_id},
#             tool_output=signal_quality,
#             node="diagnostics"
#         )
        
#         # Parse and store results
#         state["diagnostics"]["port_status"] = port_status
#         state["diagnostics"]["signal_quality"] = signal_quality
#         state["diagnostics"]["area_outages"] = area_outages
        
#         # Determine if provider issue
#         provider_issue = False
#         issue_type = None
#         estimated_fix = None
        
#         # Check for area outage
#         if area_outages.get("success") and area_outages.get("outage_detected"):
#             provider_issue = True
#             issue_type = "area_outage"
#             estimated_fix = area_outages.get("estimated_fix_time", "2 valandos")
        
#         # Check for port issues
#         elif port_status.get("success") and port_status.get("status") == "down":
#             provider_issue = True
#             issue_type = "port_down"
#             estimated_fix = "2 valandos"
        
#         # Check for signal issues
#         elif signal_quality.get("success") and signal_quality.get("quality") == "poor":
#             provider_issue = True
#             issue_type = "signal_degradation"
#             estimated_fix = "1 valanda"
        
#         state["diagnostics"]["provider_issue"] = provider_issue
#         state["diagnostics"]["issue_type"] = issue_type if provider_issue else None
#         state["diagnostics"]["estimated_fix_time"] = estimated_fix if provider_issue else None
        
#         state["diagnostics_completed"] = True
#         state["current_node"] = "diagnostics"
        
#         return {
#             "diagnostics": state["diagnostics"],
#             "diagnostics_completed": True,
#             "tool_calls": state["tool_calls"],
#             "messages": state["messages"],
#             "current_node": state["current_node"]
#         }
        
#     except Exception as e:
#         state = add_error(
#             state=state,
#             error_message=f"Diagnostics failed: {str(e)}",
#             node="diagnostics",
#             error_type="mcp_tool_error"
#         )
        
#         return {
#             "diagnostics_completed": False,
#             "errors": state["errors"],
#             "last_error": state["last_error"],
#             "current_node": "diagnostics"
#         }

"""
Diagnostics Node - Check provider-side issues
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

from src.services.network import check_provider_issues
from src.graph.state import add_message, _get_attr

logger = get_logger(__name__)


def diagnostics_node(state) -> dict:
    """
    Diagnostics node - checks provider-side issues.
    
    Performs:
    - Area outage check (critical provider issue)
    - Port status check (informational)
    - IP assignment check (informational)
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with diagnostic results
    """
    logger.info("=== Diagnostics Node ===")
    
    customer_id = _get_attr(state, "customer_id")
    
    if not customer_id:
        logger.error("No customer_id in state")
        return {
            "current_node": "diagnostics",
            "last_error": "No customer ID"
        }
    
    logger.info(f"Running diagnostics for customer: {customer_id}")
    
    # Inform customer
    checking_message = add_message(
        role="assistant",
        content="Vienu momentu, tikrinu ar nėra gedimų jūsų rajone ir jūsų ryšio parametrus...",
        node="diagnostics"
    )
    
    try:
        # Run provider diagnostics
        results = check_provider_issues(customer_id)
        
        logger.info(f"Diagnostics: provider_issue={results['provider_issue']}, "
                   f"needs_troubleshooting={results['needs_troubleshooting']}")
        
        # Build informative message about what was found
        info_parts = []
        
        for issue in results.get("issues_found", []):
            if issue["type"] == "area_outage":
                info_parts.append("• Aptiktas gedimas jūsų rajone")
            elif issue["type"] == "port_down":
                info_parts.append("• Tinklo portas neaktyvus")
            elif issue["type"] == "no_ip":
                info_parts.append("• Nėra aktyvaus IP priskyrimo")
        
        if info_parts:
            info_message = add_message(
                role="assistant",
                content="Diagnostikos rezultatai:\n" + "\n".join(info_parts),
                node="diagnostics"
            )
            messages = [checking_message, info_message]
        else:
            # No issues found
            ok_message = add_message(
                role="assistant",
                content="Tiekėjo pusėje gedimų neaptikta. Bandykime patikrinti jūsų įrangą.",
                node="diagnostics"
            )
            messages = [checking_message, ok_message]
        
        return {
            "messages": messages,
            "current_node": "diagnostics",
            "diagnostics_completed": True,
            "provider_issue_detected": results["provider_issue"],
            "needs_troubleshooting": results.get("needs_troubleshooting", False),
            "diagnostic_results": results,
        }
        
    except Exception as e:
        logger.error(f"Diagnostics error: {e}", exc_info=True)
        
        error_message = add_message(
            role="assistant",
            content="Atsiprašau, įvyko klaida tikrinant sistemą. Bandykime spręsti problemą kitais būdais.",
            node="diagnostics"
        )
        
        return {
            "messages": [checking_message, error_message],
            "current_node": "diagnostics",
            "diagnostics_completed": True,
            "provider_issue_detected": False,
            "needs_troubleshooting": True,  # Assume needs troubleshooting
            "last_error": str(e)
        }


def diagnostics_router(state) -> str:
    """
    Route after diagnostics.
    
    Logic:
    - Area outage detected → inform customer (provider issue)
    - Other issues or unclear → try troubleshooting
    
    Returns:
        - "inform_provider_issue" → critical provider problem (area outage)
        - "troubleshooting" → needs customer-side troubleshooting
    """
    provider_issue = _get_attr(state, "provider_issue_detected", False)
    
    if provider_issue:
        logger.info("Critical provider issue (area outage) → inform_provider_issue")
        return "inform_provider_issue"
    
    # No critical provider issue - try troubleshooting
    logger.info("No critical provider issue → troubleshooting")
    return "troubleshooting"