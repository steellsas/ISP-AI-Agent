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
            node="diagnostics",
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
        role="assistant", content=t("diagnostics.checking"), node="diagnostics"
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
                role="assistant", content="\n".join(info_parts), node="diagnostics"
            )
            messages.append(info_message)

        else:
            # No issues found - proceed to troubleshooting
            ok_message = add_message(
                role="assistant", content=t("diagnostics.no_issues"), node="diagnostics"
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
            role="assistant", content=t("diagnostics.error"), node="diagnostics"
        )

        return {
            "messages": [checking_message, error_message],
            "current_node": "diagnostics",
            "diagnostics_completed": True,
            "provider_issue_detected": False,
            "needs_troubleshooting": True,  # Assume needs troubleshooting on error
            "last_error": str(e),
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
