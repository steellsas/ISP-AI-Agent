"""
Test Edge Routers
Unit tests for conditional routing logic
"""

import pytest
from src.graph.state import ConversationState, create_initial_state
from src.graph.edges import (
    customer_identification_router,
    address_confirmation_router,
    diagnostics_router,
    closing_router
)


# ========== TEST FIXTURES ==========

@pytest.fixture
def base_state():
    """Create base state for testing."""
    return create_initial_state(
        conversation_id="test-123",
        phone_number="+37060000001",
        language="lt"
    )


# ========== CUSTOMER IDENTIFICATION ROUTER TESTS ==========

def test_customer_identification_router_found(base_state):
    """Test routing when customer is found."""
    # Setup state
    base_state["customer_identified"] = True
    base_state["customer"]["customer_id"] = "CUST001"
    
    # Call router
    next_node = customer_identification_router(base_state)
    
    # Assert
    assert next_node == "address_confirmation"


def test_customer_identification_router_not_found(base_state):
    """Test routing when customer is not found."""
    # Setup state
    base_state["customer_identified"] = False
    
    # Call router
    next_node = customer_identification_router(base_state)
    
    # Assert
    assert next_node == "closing"


def test_customer_identification_router_multiple_addresses(base_state):
    """Test routing when customer has multiple addresses."""
    # Setup state
    base_state["customer_identified"] = True
    base_state["customer"]["addresses"] = [
        {"address_id": "1", "city": "Šiauliai"},
        {"address_id": "2", "city": "Vilnius"}
    ]
    
    # Call router
    next_node = customer_identification_router(base_state)
    
    # Assert (for now goes to confirmation, later: address_selection)
    assert next_node == "address_confirmation"


# ========== ADDRESS CONFIRMATION ROUTER TESTS ==========

def test_address_confirmation_router_confirmed(base_state):
    """Test routing when address is confirmed."""
    # Setup state
    base_state["address_confirmed"] = True
    
    # Call router
    next_node = address_confirmation_router(base_state)
    
    # Assert
    assert next_node == "diagnostics"


def test_address_confirmation_router_not_confirmed(base_state):
    """Test routing when address is not confirmed."""
    # Setup state
    base_state["address_confirmed"] = False
    
    # Call router
    next_node = address_confirmation_router(base_state)
    
    # Assert (for now goes to closing, later: address_search)
    assert next_node == "closing"


# ========== DIAGNOSTICS ROUTER TESTS ==========

def test_diagnostics_router_provider_issue(base_state):
    """Test routing when provider issue detected."""
    # Setup state
    base_state["diagnostics"]["provider_issue"] = True
    base_state["diagnostics"]["issue_type"] = "outage"
    
    # Call router
    next_node = diagnostics_router(base_state)
    
    # Assert
    assert next_node == "inform_provider_issue"


def test_diagnostics_router_client_issue(base_state):
    """Test routing when client-side issue."""
    # Setup state
    base_state["diagnostics"]["provider_issue"] = False
    
    # Call router
    next_node = diagnostics_router(base_state)
    
    # Assert (for now goes to closing, later: troubleshooting)
    assert next_node == "closing"


def test_diagnostics_router_no_diagnostics(base_state):
    """Test routing when diagnostics incomplete."""
    # Setup state (no diagnostics run)
    base_state["diagnostics_completed"] = False
    
    # Call router
    next_node = diagnostics_router(base_state)
    
    # Assert (defaults to closing when unclear)
    assert next_node == "closing"


# ========== CLOSING ROUTER TESTS ==========

def test_closing_router_wants_more_help(base_state):
    """Test routing when user wants more help."""
    # Setup state
    base_state["next_action"] = "restart"
    base_state["conversation_ended"] = False
    
    # Call router
    next_node = closing_router(base_state)
    
    # Assert
    assert next_node == "problem_capture"


def test_closing_router_conversation_ended(base_state):
    """Test routing when conversation ends."""
    # Setup state
    base_state["conversation_ended"] = True
    base_state["next_action"] = None
    
    # Call router
    next_node = closing_router(base_state)
    
    # Assert
    assert next_node == "__end__"


def test_closing_router_default_end(base_state):
    """Test default routing (end conversation)."""
    # Setup state (no restart signal)
    base_state["conversation_ended"] = False
    base_state["next_action"] = None
    
    # Call router
    next_node = closing_router(base_state)
    
    # Assert
    assert next_node == "__end__"


# ========== INTEGRATION TESTS ==========

def test_router_integration_happy_path(base_state):
    """Test complete happy path routing."""
    
    # 1. Customer found
    base_state["customer_identified"] = True
    assert customer_identification_router(base_state) == "address_confirmation"
    
    # 2. Address confirmed
    base_state["address_confirmed"] = True
    assert address_confirmation_router(base_state) == "diagnostics"
    
    # 3. Provider issue detected
    base_state["diagnostics"]["provider_issue"] = True
    assert diagnostics_router(base_state) == "inform_provider_issue"
    
    # 4. Conversation ends
    base_state["conversation_ended"] = True
    assert closing_router(base_state) == "__end__"


def test_router_integration_customer_not_found(base_state):
    """Test routing when customer not found."""
    
    # 1. Customer not found
    base_state["customer_identified"] = False
    assert customer_identification_router(base_state) == "closing"
    
    # 2. Conversation ends
    base_state["conversation_ended"] = True
    assert closing_router(base_state) == "__end__"


def test_router_integration_loop_back(base_state):
    """Test routing loop back for another issue."""
    
    # Complete first issue
    base_state["customer_identified"] = True
    base_state["address_confirmed"] = True
    base_state["diagnostics"]["provider_issue"] = True
    
    # User wants more help
    base_state["next_action"] = "restart"
    base_state["conversation_ended"] = False
    
    # Should loop back to problem_capture
    assert closing_router(base_state) == "problem_capture"


# ========== EDGE CASE TESTS ==========

def test_router_missing_state_fields(base_state):
    """Test routers handle missing state fields gracefully."""
    
    # Empty state (missing fields)
    minimal_state = ConversationState(
        conversation_id="test",
        session_start="2024-01-01",
        language="lt",
        current_node="test",
        messages=[],
        customer={},
        customer_identified=False,
        address_confirmed=False,
        authentication_required=False,
        authenticated=False,
        problem={},
        problem_identified=False,
        diagnostics={},
        diagnostics_completed=False,
        troubleshooting={
            "steps_taken": [],
            "instructions_given": [],
            "customer_actions": [],
            "resolved": False,
            "retry_count": 0,
            "max_retries": 3
        },
        troubleshooting_attempted=False,
        ticket={},
        ticket_created=False,
        next_action=None,
        requires_escalation=False,
        conversation_ended=False,
        waiting_for_user_input=False,
        last_question=None,
        retrieved_documents=[],
        tool_calls=[],
        errors=[],
        last_error=None,
        metadata={}
    )
    
    # Should not crash
    assert customer_identification_router(minimal_state) == "closing"
    assert address_confirmation_router(minimal_state) == "closing"
    assert diagnostics_router(minimal_state) == "closing"
    assert closing_router(minimal_state) == "__end__"


# ========== RUN TESTS ==========

if __name__ == "__main__":
    pytest.main([__file__, "-v"])