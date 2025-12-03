
# """
# Diagnostics Node - Check provider-side issues
# """

# import sys
# import logging
# from pathlib import Path

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

# from src.services.network import check_provider_issues
# from src.graph.state import add_message, _get_attr

# logger = get_logger(__name__)


# def diagnostics_node(state) -> dict:
#     """
#     Diagnostics node - checks provider-side issues.
    
#     Performs:
#     - Area outage check (critical provider issue)
#     - Port status check (informational)
#     - IP assignment check (informational)
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         State update with diagnostic results
#     """
#     logger.info("=== Diagnostics Node ===")
    
#     customer_id = _get_attr(state, "customer_id")
    
#     if not customer_id:
#         logger.error("No customer_id in state")
#         return {
#             "current_node": "diagnostics",
#             "last_error": "No customer ID"
#         }
    
#     logger.info(f"Running diagnostics for customer: {customer_id}")
    
#     # Inform customer
#     checking_message = add_message(
#         role="assistant",
#         content="Vienu momentu, tikrinu ar nėra gedimų jūsų rajone ir jūsų ryšio parametrus...",
#         node="diagnostics"
#     )
    
#     try:
#         # Run provider diagnostics
#         results = check_provider_issues(customer_id)
        
#         logger.info(f"Diagnostics: provider_issue={results['provider_issue']}, "
#                    f"needs_troubleshooting={results['needs_troubleshooting']}")
        
#         # Build informative message about what was found
#         info_parts = []
        
#         for issue in results.get("issues_found", []):
#             if issue["type"] == "area_outage":
#                 info_parts.append("• Aptiktas gedimas jūsų rajone")
#             elif issue["type"] == "port_down":
#                 info_parts.append("• Tinklo portas neaktyvus")
#             elif issue["type"] == "no_ip":
#                 info_parts.append("• Nėra aktyvaus IP priskyrimo")
        
#         if info_parts:
#             info_message = add_message(
#                 role="assistant",
#                 content="Diagnostikos rezultatai:\n" + "\n".join(info_parts),
#                 node="diagnostics"
#             )
#             messages = [checking_message, info_message]
#         else:
#             # No issues found
#             ok_message = add_message(
#                 role="assistant",
#                 content="Tiekėjo pusėje gedimų neaptikta. Bandykime patikrinti jūsų įrangą.",
#                 node="diagnostics"
#             )
#             messages = [checking_message, ok_message]
        
#         return {
#             "messages": messages,
#             "current_node": "diagnostics",
#             "diagnostics_completed": True,
#             "provider_issue_detected": results["provider_issue"],
#             "needs_troubleshooting": results.get("needs_troubleshooting", False),
#             "diagnostic_results": results,
#         }
        
#     except Exception as e:
#         logger.error(f"Diagnostics error: {e}", exc_info=True)
        
#         error_message = add_message(
#             role="assistant",
#             content="Atsiprašau, įvyko klaida tikrinant sistemą. Bandykime spręsti problemą kitais būdais.",
#             node="diagnostics"
#         )
        
#         return {
#             "messages": [checking_message, error_message],
#             "current_node": "diagnostics",
#             "diagnostics_completed": True,
#             "provider_issue_detected": False,
#             "needs_troubleshooting": True,  # Assume needs troubleshooting
#             "last_error": str(e)
#         }


# def diagnostics_router(state) -> str:
#     """
#     Route after diagnostics.
    
#     Logic:
#     - Area outage detected → inform customer (provider issue)
#     - Other issues or unclear → try troubleshooting
    
#     Returns:
#         - "inform_provider_issue" → critical provider problem (area outage)
#         - "troubleshooting" → needs customer-side troubleshooting
#     """
#     provider_issue = _get_attr(state, "provider_issue_detected", False)
    
#     if provider_issue:
#         logger.info("Critical provider issue (area outage) → inform_provider_issue")
#         return "inform_provider_issue"
    
#     # No critical provider issue - try troubleshooting
#     logger.info("No critical provider issue → troubleshooting")
#     return "troubleshooting"



"""
Diagnostics Node - Check provider-side issues

Runs network diagnostics and reports results.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.graph.state import add_message, _get_attr
from src.services.network import check_provider_issues
from src.services.language_service import get_language
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# NODE FUNCTION
# =============================================================================

def diagnostics_node(state: Any) -> dict:
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
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    customer_id = _get_attr(state, "customer_id")
    
    logger.info(f"[{conversation_id}] Diagnostics node started | customer_id={customer_id}")
    
    # Validate customer_id
    if not customer_id:
        logger.error(f"[{conversation_id}] No customer_id in state")
        
        error_message = add_message(
            role="assistant",
            content=t("errors.no_customer_id", default="Nepavyko identifikuoti kliento."),
            node="diagnostics"
        )
        
        return {
            "messages": [error_message],
            "current_node": "diagnostics",
            "last_error": "No customer ID",
            "diagnostics_completed": True,
            "needs_troubleshooting": True,
        }
    
    # Inform customer that diagnostics is starting
    checking_message = add_message(
        role="assistant",
        content=t("diagnostics.checking"),
        node="diagnostics"
    )
    
    try:
        # Run provider diagnostics
        results = check_provider_issues(customer_id)
        
        provider_issue = results.get("provider_issue", False)
        needs_troubleshooting = results.get("needs_troubleshooting", True)
        issues_found = results.get("issues_found", [])
        
        logger.info(
            f"[{conversation_id}] Diagnostics completed | "
            f"provider_issue={provider_issue} | "
            f"needs_troubleshooting={needs_troubleshooting} | "
            f"issues_count={len(issues_found)}"
        )
        
        # Build result message
        messages = [checking_message]
        
        if issues_found:
            # Build issues list
            info_parts = [t("diagnostics.results_header")]
            
            for issue in issues_found:
                issue_type = issue.get("type", "unknown")
                
                if issue_type == "area_outage":
                    info_parts.append(t("diagnostics.issue_area_outage"))
                elif issue_type == "port_down":
                    info_parts.append(t("diagnostics.issue_port_down"))
                elif issue_type == "no_ip":
                    info_parts.append(t("diagnostics.issue_no_ip"))
                else:
                    info_parts.append(f"• {issue_type}")
            
            info_message = add_message(
                role="assistant",
                content="\n".join(info_parts),
                node="diagnostics"
            )
            messages.append(info_message)
            
        else:
            # No issues found - proceed to troubleshooting
            ok_message = add_message(
                role="assistant",
                content=t("diagnostics.no_issues"),
                node="diagnostics"
            )
            messages.append(ok_message)
        
        return {
            "messages": messages,
            "current_node": "diagnostics",
            "diagnostics_completed": True,
            "provider_issue_detected": provider_issue,
            "needs_troubleshooting": needs_troubleshooting,
            "diagnostic_results": results,
        }
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Diagnostics error: {e}", exc_info=True)
        
        error_message = add_message(
            role="assistant",
            content=t("diagnostics.error"),
            node="diagnostics"
        )
        
        return {
            "messages": [checking_message, error_message],
            "current_node": "diagnostics",
            "diagnostics_completed": True,
            "provider_issue_detected": False,
            "needs_troubleshooting": True,  # Assume needs troubleshooting on error
            "last_error": str(e)
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================

def diagnostics_router(state: Any) -> str:
    """
    Route after diagnostics.
    
    Logic:
    - Area outage detected → inform customer (provider issue)
    - Other issues or unclear → try troubleshooting
    
    Returns:
        - "inform_provider_issue" → critical provider problem (area outage)
        - "troubleshooting" → needs customer-side troubleshooting
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    provider_issue = _get_attr(state, "provider_issue_detected", False)
    
    if provider_issue:
        logger.info(f"[{conversation_id}] Router → inform_provider_issue (critical provider issue)")
        return "inform_provider_issue"
    
    logger.info(f"[{conversation_id}] Router → troubleshooting (no critical provider issue)")
    return "troubleshooting"
