"""
LangGraph Workflow - ISP Support Agent

Flow:
1. First invoke (no messages): START → greeting → END
2. Subsequent invokes (with user message): START → problem_capture ⟲ → END/next

Uses entry_router to determine which path to take.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import State, _get_messages, _get_attr

from src.graph.nodes import (
    greeting_node, 
    problem_capture_node, 
    problem_capture_router,
    phone_lookup_node,
    phone_lookup_router,
    address_confirmation_node,
    address_confirmation_router,
    address_search_node,
    address_search_router,
    diagnostics_node,
    diagnostics_router,
    inform_provider_issue_node,
    troubleshooting_node,
    troubleshooting_router,
)

# Global checkpointer - must be module level for persistence
_memory_saver = MemorySaver()


def entry_router(state) -> str:
    """
    Determine entry point based on conversation state.
    """
    messages = _get_messages(state)
    
    if not messages:
        return "greeting"
    
    customer_id = _get_attr(state, "customer_id")
    address_confirmed = _get_attr(state, "address_confirmed")
    problem_description = _get_attr(state, "problem_description")
    address_search_successful = _get_attr(state, "address_search_successful")
    diagnostics_completed = _get_attr(state, "diagnostics_completed")
    troubleshooting_scenario_id = _get_attr(state, "troubleshooting_scenario_id")
    
    # If in troubleshooting flow
    if troubleshooting_scenario_id:
        return "troubleshooting"
    
    # If diagnostics completed, should be in troubleshooting or inform
    if diagnostics_completed:
        return "troubleshooting"
    
    # If in address search flow
    if customer_id is None and problem_description and address_search_successful is None:
        return "address_search"
    
    # If we have customer but address not confirmed
    if customer_id and address_confirmed is None:
        return "address_confirmation"
    
    # If problem not captured yet
    if not problem_description:
        return "problem_capture"
    
    return "problem_capture"


def create_graph() -> StateGraph:
    """
    Create the ISP support agent workflow.
    
    Current nodes:
    - greeting: Static greeting from config
    - problem_capture: LLM analyzes problem, loops until clear
    
    Returns:
        Compiled StateGraph
    """
    # Initialize graph with Pydantic state schema
    workflow = StateGraph(State)
    
    # === ADD NODES ===
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("problem_capture", problem_capture_node)
    workflow.add_node("phone_lookup", phone_lookup_node)
    workflow.add_node("address_confirmation", address_confirmation_node)
    workflow.add_node("address_search", address_search_node)
    workflow.add_node("diagnostics", diagnostics_node)
    workflow.add_node("inform_provider_issue", inform_provider_issue_node)
    workflow.add_node("troubleshooting", troubleshooting_node)
    # === EDGES ===
    
    # START → router decides greeting or problem_capture
    workflow.add_conditional_edges(
        START,
        entry_router,
        {
            "greeting": "greeting",
            "problem_capture": "problem_capture",
            "address_confirmation": "address_confirmation",
            "address_search": "address_search",
            "troubleshooting": "troubleshooting",
        }
    )
    
    # greeting → END (wait for user input)
    workflow.add_edge("greeting", END)
    
    workflow.add_conditional_edges(
        "problem_capture",
        problem_capture_router,
            {
                "problem_capture": "problem_capture",  
                "phone_lookup": "phone_lookup",        
                "end": END,
            }
        )

    # phone_lookup → conditional routing
    workflow.add_conditional_edges(
            "phone_lookup",
            phone_lookup_router,
            {
                "address_confirmation": "address_confirmation",
                "address_selection": END,      # TODO: pridėsim vėliau  
                "address_search": "address_search",
            }
        )
    workflow.add_conditional_edges(
            "address_confirmation",
            address_confirmation_router,
            {
                "address_confirmation": "address_confirmation",  # Loop
                "diagnostics": "diagnostics",
                "address_search": "address_search",    # ← PAKEISTA
                "end": END,
            }
        )

    workflow.add_conditional_edges(
        "address_search",
        address_search_router,
        {
            "diagnostics": "diagnostics", 
            "closing": END,          # TODO: pridėsim vėliau
            "end": END,              # Wait for user input
        }
    )
    # diagnostics → conditional routing
    workflow.add_conditional_edges(
        "diagnostics",
        diagnostics_router,
        {
            "inform_provider_issue": "inform_provider_issue",
             "troubleshooting": "troubleshooting"
        }
    )

    workflow.add_edge("inform_provider_issue", END)

    # troubleshooting → conditional routing
    workflow.add_conditional_edges(
        "troubleshooting",
        troubleshooting_router,
        {
            "troubleshooting": "troubleshooting",  # Loop back (wait for user)
            "create_ticket": END,     # TODO: pridėsim vėliau
            "closing": END,           # TODO: pridėsim vėliau
            "end": END,               # Wait for user input
        }
    )

 
    # === COMPILE ===
    compiled = workflow.compile(checkpointer=_memory_saver)
    
    return compiled


# Create app instance
app = create_graph()


def get_app() -> StateGraph:
    """Get the compiled workflow app."""
    return app


def get_memory_saver() -> MemorySaver:
    """Get memory saver for debugging."""
    return _memory_saver