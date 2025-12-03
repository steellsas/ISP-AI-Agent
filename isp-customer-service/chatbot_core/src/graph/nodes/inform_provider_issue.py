
# """
# Inform Provider Issue Node - Tell customer about provider-side problems
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

# from src.graph.state import add_message, _get_attr

# logger = get_logger(__name__)


# def inform_provider_issue_node(state) -> dict:
#     """
#     Inform provider issue node - explains provider-side problems to customer.
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         State update with informative message
#     """
#     logger.info("=== Inform Provider Issue Node ===")
    
#     diagnostic_results = _get_attr(state, "diagnostic_results", {})
#     issues_found = diagnostic_results.get("issues_found", [])
    
#     # Filter to only provider issues (area outages)
#     provider_issues = [i for i in issues_found if i.get("source") == "provider"]
    
#     if not provider_issues:
#         # Generic message
#         message_text = ("Aptikome problemą mūsų tinkle. Mūsų specialistai jau dirba "
#                        "prie jos sprendimo. Atsiprašome už nepatogumus.\n\n"
#                        "Informuosime jus, kai problema bus išspręsta.")
#     else:
#         # Specific issue message
#         primary_issue = provider_issues[0]
#         issue_type = primary_issue.get("type")
        
#         if issue_type == "area_outage":
#             outages = primary_issue.get("outages", [])
#             if outages:
#                 outage = outages[0]
#                 est_resolution = outage.get("estimated_resolution")
                
#                 outage_type_map = {
#                     "internet": "interneto",
#                     "tv": "televizijos",
#                     "phone": "telefono",
#                     "all": "visų paslaugų"
#                 }
                
#                 outage_type_lt = outage_type_map.get(
#                     outage.get("outage_type", ""),
#                     "paslaugos"
#                 )
                
#                 message_text = (
#                     f"Šiuo metu jūsų rajone vyksta {outage_type_lt} gedimas. "
#                     f"Mūsų specialistai aktyviai dirba prie sprendimo."
#                 )
                
#                 if est_resolution:
#                     message_text += f" Tikimasi išspręsti iki: {est_resolution}."
                
#                 affected = outage.get("affected_customers")
#                 if affected:
#                     message_text += f"\n\nPaveikta apie {affected} klientų rajone."
                
#                 description = outage.get("description")
#                 if description:
#                     message_text += f"\n\nDetalės: {description}"
#             else:
#                 message_text = "Aptikome gedimą jūsų rajone. Specialistai jau dirba prie sprendimo."
        
#         else:
#             message_text = ("Aptikome techninę problemą mūsų tinkle. "
#                            "Specialistai dirba prie sprendimo.")
        
#         message_text += "\n\nAtsiprašome už nepatogumus. Ar yra dar kažkas, kuo galėčiau padėti?"
    
#     logger.info(f"Informing about {len(provider_issues)} provider issue(s)")
    
#     message = add_message(
#         role="assistant",
#         content=message_text,
#         node="inform_provider_issue"
#     )
    
#     return {
#         "messages": [message],
#         "current_node": "inform_provider_issue",
#         "provider_issue_informed": True,
#     }


"""
Inform Provider Issue Node - Tell customer about provider-side problems

Explains provider-side issues (outages, maintenance) to customer.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.graph.state import add_message, _get_attr
from src.services.language_service import get_language
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_outage_type_name(outage_type: str) -> str:
    """
    Get translated outage type name.
    
    Args:
        outage_type: Outage type code (internet, tv, phone, all)
        
    Returns:
        Translated outage type name
    """
    type_key = f"provider_issue.outage_types.{outage_type}"
    return t(type_key, default=t("provider_issue.outage_types.default"))


def _build_outage_message(issue: dict) -> str:
    """
    Build detailed outage message from issue data.
    
    Args:
        issue: Issue dict with type, outages, etc.
        
    Returns:
        Formatted message string
    """
    outages = issue.get("outages", [])
    
    if not outages:
        return t("provider_issue.generic")
    
    outage = outages[0]
    outage_type = outage.get("outage_type", "default")
    outage_type_name = _get_outage_type_name(outage_type)
    estimated_resolution = outage.get("estimated_resolution")
    affected_customers = outage.get("affected_customers")
    description = outage.get("description")
    
    # Build message
    if estimated_resolution:
        message = t(
            "provider_issue.area_outage_eta",
            outage_type=outage_type_name,
            estimated_resolution=estimated_resolution
        )
    else:
        message = t(
            "provider_issue.area_outage",
            outage_type=outage_type_name
        )
    
    # Add affected customers info
    if affected_customers:
        message += "\n\n" + t(
            "provider_issue.affected_customers",
            count=affected_customers
        )
    
    # Add description
    if description:
        message += "\n\n" + t(
            "provider_issue.details",
            description=description
        )
    
    return message


# =============================================================================
# NODE FUNCTION
# =============================================================================

def inform_provider_issue_node(state: Any) -> dict:
    """
    Inform provider issue node - explains provider-side problems to customer.
    
    Scenarios:
    - Area outage (internet, tv, phone, all)
    - Scheduled maintenance
    - Generic network issue
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with informative message
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Inform provider issue node started")
    
    try:
        diagnostic_results = _get_attr(state, "diagnostic_results", {})
        issues_found = diagnostic_results.get("issues_found", [])
        
        # Filter to only provider issues (area outages)
        provider_issues = [i for i in issues_found if i.get("source") == "provider"]
        
        logger.info(f"[{conversation_id}] Provider issues count: {len(provider_issues)}")
        
        if not provider_issues:
            # No specific provider issues - generic message
            message_text = t("provider_issue.generic")
        else:
            # Build message for primary issue
            primary_issue = provider_issues[0]
            issue_type = primary_issue.get("type")
            
            if issue_type == "area_outage":
                message_text = _build_outage_message(primary_issue)
            elif issue_type == "maintenance":
                end_time = primary_issue.get("end_time", "")
                message_text = t(
                    "provider_issue.maintenance",
                    end_time=end_time
                )
            else:
                message_text = t("provider_issue.generic")
        
        # Add apology and offer help
        message_text += "\n\n" + t("provider_issue.apology")
        
        message = add_message(
            role="assistant",
            content=message_text,
            node="inform_provider_issue"
        )
        
        logger.info(f"[{conversation_id}] Provider issue informed | lang={get_language()}")
        
        return {
            "messages": [message],
            "current_node": "inform_provider_issue",
            "provider_issue_informed": True,
        }
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Inform provider issue error: {e}", exc_info=True)
        
        # Fallback message
        fallback_message = add_message(
            role="assistant",
            content=t("provider_issue.generic") + "\n\n" + t("provider_issue.apology"),
            node="inform_provider_issue"
        )
        
        return {
            "messages": [fallback_message],
            "current_node": "inform_provider_issue",
            "provider_issue_informed": True,
            "last_error": str(e)
        }
