"""
Edge Conditions
Reusable condition functions for routing decisions
"""

from typing import Any, Dict
from ..state import ConversationState


def is_customer_found(state: ConversationState) -> bool:
    """
    Check if customer was found.
    
    Args:
        state: Current state
        
    Returns:
        True if customer identified
    """
    return state.get("customer_identified", False)


def is_address_confirmed(state: ConversationState) -> bool:
    """
    Check if address was confirmed.
    
    Args:
        state: Current state
        
    Returns:
        True if address confirmed
    """
    return state.get("address_confirmed", False)


def is_provider_issue(state: ConversationState) -> bool:
    """
    Check if issue is on provider side.
    
    Args:
        state: Current state
        
    Returns:
        True if provider issue detected
    """
    return state.get("diagnostics", {}).get("provider_issue", False)


def is_authenticated(state: ConversationState) -> bool:
    """
    Check if customer is authenticated.
    
    Args:
        state: Current state
        
    Returns:
        True if authenticated
    """
    return state.get("authenticated", False)


def needs_authentication(state: ConversationState) -> bool:
    """
    Check if authentication is required.
    
    Args:
        state: Current state
        
    Returns:
        True if authentication needed
    """
    return state.get("authentication_required", False)


def is_problem_resolved(state: ConversationState) -> bool:
    """
    Check if problem was resolved.
    
    Args:
        state: Current state
        
    Returns:
        True if resolved
    """
    return state.get("troubleshooting", {}).get("resolved", False)


def should_escalate(state: ConversationState) -> bool:
    """
    Check if issue should be escalated.
    
    Args:
        state: Current state
        
    Returns:
        True if escalation needed
    """
    if state.get("requires_escalation", False):
        return True
    
    # Check retry count
    retry_count = state.get("troubleshooting", {}).get("retry_count", 0)
    max_retries = state.get("troubleshooting", {}).get("max_retries", 3)
    
    return retry_count >= max_retries


def has_multiple_addresses(state: ConversationState) -> bool:
    """
    Check if customer has multiple addresses.
    
    Args:
        state: Current state
        
    Returns:
        True if multiple addresses
    """
    addresses = state.get("customer", {}).get("addresses", [])
    return len(addresses) > 1


def wants_more_help(state: ConversationState) -> bool:
    """
    Check if user wants more help (from closing node).
    
    Args:
        state: Current state
        
    Returns:
        True if user wants to continue
    """
    next_action = state.get("next_action")
    return next_action == "restart"


def is_conversation_ended(state: ConversationState) -> bool:
    """
    Check if conversation has ended.
    
    Args:
        state: Current state
        
    Returns:
        True if ended
    """
    return state.get("conversation_ended", False)