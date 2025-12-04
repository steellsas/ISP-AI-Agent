

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


# """
# Graph Nodes Package

# All workflow nodes for the ISP customer service chatbot.
# Import nodes and routers from this package.

# Usage:
#     from src.graph.nodes import (
#         greeting_node,
#         problem_capture_node,
#         problem_capture_router,
#         ...
#     )
# """

# # Greeting
# from .greeting import greeting_node

# # Problem Capture
# from .problem_capture import (
#     problem_capture_node,
#     problem_capture_router,
# )

# # Phone Lookup
# from .phone_lookup import (
#     phone_lookup_node,
#     phone_lookup_router,
# )

# # Address Confirmation
# from .address_confirmation import (
#     address_confirmation_node,
#     address_confirmation_router,
# )

# # Address Search
# from .address_search import (
#     address_search_node,
#     address_search_router,
# )

# # Address Selection (if exists)
# try:
#     from .address_selection import (
#         address_selection_node,
#         address_selection_router,
#     )
# except ImportError:
#     address_selection_node = None
#     address_selection_router = None

# # Diagnostics
# from .diagnostics import (
#     diagnostics_node,
#     diagnostics_router,
# )

# # Inform Provider Issue
# from .inform_provider_issue import inform_provider_issue_node

# # Troubleshooting
# from .troubleshooting import (
#     troubleshooting_node,
#     troubleshooting_router,
# )

# # Create Ticket
# from .create_ticket import create_ticket_node

# # Closing
# from .closing import closing_node


# # =============================================================================
# # EXPORTS
# # =============================================================================

# __all__ = [
#     # Greeting
#     "greeting_node",
    
#     # Problem Capture
#     "problem_capture_node",
#     "problem_capture_router",
    
#     # Phone Lookup
#     "phone_lookup_node",
#     "phone_lookup_router",
    
#     # Address Confirmation
#     "address_confirmation_node",
#     "address_confirmation_router",
    
#     # Address Search
#     "address_search_node",
#     "address_search_router",
    
#     # Address Selection
#     "address_selection_node",
#     "address_selection_router",
    
#     # Diagnostics
#     "diagnostics_node",
#     "diagnostics_router",
    
#     # Inform Provider Issue
#     "inform_provider_issue_node",
    
#     # Troubleshooting
#     "troubleshooting_node",
#     "troubleshooting_router",
    
#     # Create Ticket
#     "create_ticket_node",
    
#     # Closing
#     "closing_node",
# ]