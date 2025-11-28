"""
Edge Routing Logic
"""

from .routers import (
    problem_capture_router,  # NEW - replaces greeting_router
    address_search_router,
    customer_identification_router,
    address_confirmation_router,
    diagnostics_router,
    troubleshooting_router,
    solution_evaluation_router,
    closing_router,
    get_router,
    ROUTER_MAP
)

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

__all__ = [
    # Routers
    "customer_identification_router",  # NEW
    "address_search_router",  # NEW
    "problem_capture_router",  # NEW - replaces greeting_router
    "customer_identification_router",
    "address_confirmation_router",
    "diagnostics_router",
    "troubleshooting_router",
    "solution_evaluation_router",
    "closing_router",
    "get_router",
    "ROUTER_MAP",
    
    # Conditions
    "is_customer_found",
    "is_address_confirmed",
    "is_provider_issue",
    "is_authenticated",
    "needs_authentication",
    "is_problem_resolved",
    "should_escalate",
    "has_multiple_addresses",
    "wants_more_help",
    "is_conversation_ended",
]

