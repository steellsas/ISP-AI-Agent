# """
# Inform Provider Issue Node
# Informs customer about provider-side issues
# """

# from typing import Dict, Any
# from ..state import ConversationState, add_message
# from ...services.llm_service import get_llm_service
# from ...config.old.prompts import PROVIDER_ISSUE_PROMPT, format_prompt


# async def inform_provider_issue_node_async(state: ConversationState) -> Dict[str, Any]:
#     """
#     Inform customer about provider issue.
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         Updated state
#     """
    
#     # Get issue details from diagnostics
#     diagnostics = state.get("diagnostics", {})
#     issue_type = diagnostics.get("issue_type", "techninė problema")
#     estimated_fix = diagnostics.get("estimated_fix_time", "artimiausiu metu")
    
#     # Use LLM to generate natural response (singleton getter)
#     llm = get_llm_service()
    
#     # Use centralized prompt with formatting
#     system_prompt = format_prompt(
#         PROVIDER_ISSUE_PROMPT,
#         issue_type=issue_type,
#         estimated_fix_time=estimated_fix
#     )
    
#     inform_message = await llm.generate(
#         system_prompt=system_prompt,
#         messages=[],
#         temperature=0.7,
#         max_tokens=200
#     )
    
#     state = add_message(
#         state=state,
#         role="assistant",
#         content=inform_message,
#         node="inform_provider_issue"
#     )
    
#     state["current_node"] = "inform_provider_issue"
#     state["requires_escalation"] = False  # Already handled by informing
    
#     return {
#         "messages": state["messages"],
#         "current_node": state["current_node"],
#         "requires_escalation": False
#     }


"""
Inform Provider Issue Node - Tell customer about provider-side problems
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

from src.graph.state import add_message, _get_attr

logger = get_logger(__name__)


def inform_provider_issue_node(state) -> dict:
    """
    Inform provider issue node - explains provider-side problems to customer.
    
    Args:
        state: Current conversation state
        
    Returns:
        State update with informative message
    """
    logger.info("=== Inform Provider Issue Node ===")
    
    diagnostic_results = _get_attr(state, "diagnostic_results", {})
    issues_found = diagnostic_results.get("issues_found", [])
    
    # Filter to only provider issues (area outages)
    provider_issues = [i for i in issues_found if i.get("source") == "provider"]
    
    if not provider_issues:
        # Generic message
        message_text = ("Aptikome problemą mūsų tinkle. Mūsų specialistai jau dirba "
                       "prie jos sprendimo. Atsiprašome už nepatogumus.\n\n"
                       "Informuosime jus, kai problema bus išspręsta.")
    else:
        # Specific issue message
        primary_issue = provider_issues[0]
        issue_type = primary_issue.get("type")
        
        if issue_type == "area_outage":
            outages = primary_issue.get("outages", [])
            if outages:
                outage = outages[0]
                est_resolution = outage.get("estimated_resolution")
                
                outage_type_map = {
                    "internet": "interneto",
                    "tv": "televizijos",
                    "phone": "telefono",
                    "all": "visų paslaugų"
                }
                
                outage_type_lt = outage_type_map.get(
                    outage.get("outage_type", ""),
                    "paslaugos"
                )
                
                message_text = (
                    f"Šiuo metu jūsų rajone vyksta {outage_type_lt} gedimas. "
                    f"Mūsų specialistai aktyviai dirba prie sprendimo."
                )
                
                if est_resolution:
                    message_text += f" Tikimasi išspręsti iki: {est_resolution}."
                
                affected = outage.get("affected_customers")
                if affected:
                    message_text += f"\n\nPaveikta apie {affected} klientų rajone."
                
                description = outage.get("description")
                if description:
                    message_text += f"\n\nDetalės: {description}"
            else:
                message_text = "Aptikome gedimą jūsų rajone. Specialistai jau dirba prie sprendimo."
        
        else:
            message_text = ("Aptikome techninę problemą mūsų tinkle. "
                           "Specialistai dirba prie sprendimo.")
        
        message_text += "\n\nAtsiprašome už nepatogumus. Ar yra dar kažkas, kuo galėčiau padėti?"
    
    logger.info(f"Informing about {len(provider_issues)} provider issue(s)")
    
    message = add_message(
        role="assistant",
        content=message_text,
        node="inform_provider_issue"
    )
    
    return {
        "messages": [message],
        "current_node": "inform_provider_issue",
        "provider_issue_informed": True,
    }