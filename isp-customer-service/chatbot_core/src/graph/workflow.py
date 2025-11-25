"""
LangGraph Workflow
Main graph definition with nodes and edges
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import Optional
import logging

from .state import ConversationState, create_initial_state

# Import nodes
from .nodes import (
    greeting_node,
    problem_capture_node,
    phone_lookup_background_node,
    address_confirmation_node,
    address_selection_node,
    address_search_node,
    diagnostics_node,
    inform_provider_issue_node,
    closing_node
)

# Import routers
from .edges import (
    problem_capture_router,
    customer_identification_router,
    address_confirmation_router,
    address_search_router,
    diagnostics_router,
    closing_router
)

logger = logging.getLogger(__name__)


# ========== GLOBAL MEMORY SAVER ==========
# CRITICAL: Must be at module level, not inside function!
# This ensures the same MemorySaver instance is used across all calls
_memory_saver = MemorySaver()


def create_workflow() -> StateGraph:
    """
    Create the ISP customer service chatbot workflow graph.
    
    Returns:
        Compiled StateGraph with checkpointing
    """
    logger.info("Creating workflow graph...")
    
    # Initialize graph with state schema
    workflow = StateGraph(ConversationState)
    
    # ========== ADD NODES ==========
    logger.info("Adding nodes...")
    
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("problem_capture", problem_capture_node)
    workflow.add_node("phone_lookup_background", phone_lookup_background_node)
    workflow.add_node("address_confirmation", address_confirmation_node)
    workflow.add_node("address_selection", address_selection_node)
    workflow.add_node("address_search", address_search_node)
    workflow.add_node("diagnostics", diagnostics_node)
    workflow.add_node("inform_provider_issue", inform_provider_issue_node)
    workflow.add_node("closing", closing_node)
    
    logger.info("Added 9 nodes")
    
    # ========== SET ENTRY POINT ==========
    workflow.set_entry_point("greeting")
    logger.info("Entry point set: greeting")
    
    # ========== ADD EDGES ==========
    logger.info("Adding edges...")

    # Simple edges
    workflow.add_edge("greeting", "problem_capture")
    workflow.add_edge("inform_provider_issue", "closing")
    workflow.add_edge("address_selection", "diagnostics")

    # Conditional edges
    workflow.add_conditional_edges(
        "problem_capture",
        problem_capture_router,
        {
            "phone_lookup_background": "phone_lookup_background",
            END: END
        }
    )

    workflow.add_conditional_edges(
        "phone_lookup_background",
        customer_identification_router,
        {
            "address_confirmation": "address_confirmation",
            "address_selection": "address_selection",
            "address_search": "address_search"
        }
    )

    workflow.add_conditional_edges(
        "address_confirmation",
        address_confirmation_router,
        {
            "diagnostics": "diagnostics",
            "address_search": "address_search"
        }
    )

    workflow.add_conditional_edges(
        "address_search",
        address_search_router,
        {
            "diagnostics": "diagnostics",
            "closing": "closing"
        }
    )

    workflow.add_conditional_edges(
        "diagnostics",
        diagnostics_router,
        {
            "inform_provider_issue": "inform_provider_issue",
            "troubleshooting": "closing",
            "closing": "closing"
        }
    )

    workflow.add_conditional_edges(
        "closing",
        closing_router,
        {
            "problem_capture": "problem_capture",
            "__end__": END
        }
    )

    logger.info("Added all edges")
    
    # ========== COMPILE WITH GLOBAL CHECKPOINTER ==========
    logger.info("Compiling graph with global checkpointer...")
    
    # Use GLOBAL memory saver (defined at module level)
    compiled = workflow.compile(checkpointer=_memory_saver)
    
    logger.info("✅ Workflow compiled successfully with MemorySaver")
    
    return compiled


# ========== GLOBAL APP INSTANCE ==========
# Create compiled app once at module load (singleton pattern)
try:
    app = create_workflow()
    logger.info("Global workflow app created")
except Exception as e:
    logger.error(f"Failed to create workflow: {e}", exc_info=True)
    app = None


def get_workflow() -> StateGraph:
    """Get the compiled workflow app."""
    if app is None:
        raise RuntimeError("Workflow not initialized. Check logs for errors.")
    return app


def get_memory_saver() -> MemorySaver:
    """Get the global memory saver for debugging."""
    return _memory_saver