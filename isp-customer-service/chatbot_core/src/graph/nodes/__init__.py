"""
Graph Nodes
All workflow nodes - async versions for LangGraph
"""

# Import async functions directly (LangGraph supports async natively!)
# from .greeting import greeting_node
# from .problem_capture import problem_capture_node, problem_capture_router

# from .problem_capture import problem_capture_node_async as problem_capture_node
# from .phone_lookup_background import phone_lookup_background_async as phone_lookup_background_node
# from .address_confirmation import address_confirmation_node_async as address_confirmation_node
# from .address_selection import address_selection_node_async as address_selection_node
# from .address_search import address_search_node_async as address_search_node
# from .diagnostics import diagnostics_node_async as diagnostics_node
# from .inform_provider_issue import inform_provider_issue_node_async as inform_provider_issue_node
# from .closing import closing_node_async as closing_node

# __all__ = [
#     "greeting_node",
#     # "problem_capture_node",
#     # "phone_lookup_background_node",
#     # "address_confirmation_node",
#     # "address_selection_node",
#     # "address_search_node",
#     # "diagnostics_node",
#     # "inform_provider_issue_node",
#     # "closing_node",
# ]

"""
Graph Nodes - All workflow nodes
"""

from .greeting import greeting_node
from .problem_capture import problem_capture_node, problem_capture_router
from .phone_lookup import phone_lookup_node, phone_lookup_router
from .address_confirmation import address_confirmation_node, address_confirmation_router
from .address_search import address_search_node, address_search_router
from .diagnostics import diagnostics_node, diagnostics_router
from .inform_provider_issue import inform_provider_issue_node
from .troubleshooting import troubleshooting_node, troubleshooting_router
from .create_ticket import create_ticket_node
from .closing import closing_node

__all__ = [
    "greeting_node",
    "problem_capture_node",
    "problem_capture_router",
    "phone_lookup_node",
    "phone_lookup_router",
    "address_confirmation_node",
    "address_confirmation_router",
    "address_search_node",
    "address_search_router",
    "diagnostics_node",
    "diagnostics_router",
    "inform_provider_issue_node",
    "troubleshooting_node",
    "troubleshooting_router",
     "create_ticket_node",
    "closing_node",
]