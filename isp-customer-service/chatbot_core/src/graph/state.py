"""
Conversation State Schema
Defines the structure of conversation state used throughout the LangGraph workflow
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal
from datetime import datetime


class CustomerInfo(TypedDict, total=False):
    """Customer identification information."""
    customer_id: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[Dict[str, Any]]
    services: Optional[List[Dict[str, Any]]]
    equipment: Optional[List[Dict[str, Any]]]


class ProblemInfo(TypedDict, total=False):
    """Problem identification information."""
    problem_type: Optional[Literal["internet", "tv", "phone", "other"]]
    category: Optional[str]  # e.g., "no_connection", "slow_speed", "intermittent"
    description: Optional[str]
    symptoms: Optional[List[str]]
    duration: Optional[str]
    affected_devices: Optional[List[str]]


class DiagnosticResults(TypedDict, total=False):
    """Network diagnostic results."""
    port_status: Optional[Dict[str, Any]]
    ip_assignment: Optional[Dict[str, Any]]
    bandwidth_history: Optional[Dict[str, Any]]
    signal_quality: Optional[Dict[str, Any]]
    ping_test: Optional[Dict[str, Any]]
    area_outages: Optional[Dict[str, Any]]
    switch_info: Optional[Dict[str, Any]]


class TroubleshootingInfo(TypedDict, total=False):
    """Troubleshooting steps and results."""
    steps_taken: List[str]
    current_step: Optional[str]
    instructions_given: List[str]
    customer_actions: List[str]
    resolved: bool


class TicketInfo(TypedDict, total=False):
    """Support ticket information."""
    ticket_id: Optional[str]
    ticket_type: Optional[str]
    priority: Optional[str]
    summary: Optional[str]
    details: Optional[str]
    created: bool


class ConversationState(TypedDict):
    """
    Main conversation state that flows through the LangGraph workflow.
    
    This state is updated by each node and contains all information
    needed to handle the customer support interaction.
    """
    
    # Conversation metadata
    conversation_id: str
    session_start: str  # ISO timestamp
    language: Literal["lt", "en"]
    current_node: str
    
    # Messages history
    messages: List[Dict[str, str]]  # role, content pairs
    
    # Customer information
    customer: CustomerInfo
    customer_identified: bool
    
    # Problem information
    problem: ProblemInfo
    problem_identified: bool
    
    # Diagnostic results
    diagnostics: DiagnosticResults
    diagnostics_completed: bool
    
    # Troubleshooting
    troubleshooting: TroubleshootingInfo
    troubleshooting_attempted: bool
    
    # Ticket
    ticket: TicketInfo
    ticket_created: bool
    
    # Workflow control
    next_action: Optional[str]  # What to do next
    requires_escalation: bool
    conversation_ended: bool
    
    # RAG context
    retrieved_documents: List[Dict[str, Any]]
    
    # MCP tool calls history
    tool_calls: List[Dict[str, Any]]
    
    # Additional context
    metadata: Dict[str, Any]


def create_initial_state(
    conversation_id: str,
    language: str = "lt"
) -> ConversationState:
    """
    Create initial conversation state.
    
    Args:
        conversation_id: Unique conversation ID
        language: Conversation language (lt or en)
        
    Returns:
        Initial ConversationState
    """
    return ConversationState(
        conversation_id=conversation_id,
        session_start=datetime.now().isoformat(),
        language=language,
        current_node="greeting",
        messages=[],
        customer=CustomerInfo(),
        customer_identified=False,
        problem=ProblemInfo(),
        problem_identified=False,
        diagnostics=DiagnosticResults(),
        diagnostics_completed=False,
        troubleshooting=TroubleshootingInfo(
            steps_taken=[],
            instructions_given=[],
            customer_actions=[],
            resolved=False
        ),
        troubleshooting_attempted=False,
        ticket=TicketInfo(created=False),
        ticket_created=False,
        next_action=None,
        requires_escalation=False,
        conversation_ended=False,
        retrieved_documents=[],
        tool_calls=[],
        metadata={}
    )


def add_message(
    state: ConversationState,
    role: str,
    content: str
) -> ConversationState:
    """
    Add a message to conversation history.
    
    Args:
        state: Current state
        role: Message role (user, assistant, system)
        content: Message content
        
    Returns:
        Updated state
    """
    state["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    return state


def get_last_user_message(state: ConversationState) -> Optional[str]:
    """
    Get the last user message.
    
    Args:
        state: Current state
        
    Returns:
        Last user message content or None
    """
    user_messages = [msg for msg in state["messages"] if msg["role"] == "user"]
    if user_messages:
        return user_messages[-1]["content"]
    return None


def get_conversation_history(
    state: ConversationState,
    limit: Optional[int] = None
) -> List[Dict[str, str]]:
    """
    Get conversation history.
    
    Args:
        state: Current state
        limit: Maximum number of recent messages (None for all)
        
    Returns:
        List of messages
    """
    messages = state["messages"]
    if limit:
        return messages[-limit:]
    return messages


def update_customer_info(
    state: ConversationState,
    customer_data: Dict[str, Any]
) -> ConversationState:
    """
    Update customer information in state.
    
    Args:
        state: Current state
        customer_data: Customer data from CRM
        
    Returns:
        Updated state
    """
    state["customer"].update(customer_data)
    state["customer_identified"] = True
    return state


def update_problem_info(
    state: ConversationState,
    problem_data: Dict[str, Any]
) -> ConversationState:
    """
    Update problem information in state.
    
    Args:
        state: Current state
        problem_data: Problem details
        
    Returns:
        Updated state
    """
    state["problem"].update(problem_data)
    state["problem_identified"] = True
    return state


def add_diagnostic_result(
    state: ConversationState,
    diagnostic_type: str,
    result: Dict[str, Any]
) -> ConversationState:
    """
    Add diagnostic result to state.
    
    Args:
        state: Current state
        diagnostic_type: Type of diagnostic
        result: Diagnostic result data
        
    Returns:
        Updated state
    """
    state["diagnostics"][diagnostic_type] = result
    return state


def add_tool_call(
    state: ConversationState,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Dict[str, Any]
) -> ConversationState:
    """
    Record MCP tool call in state.
    
    Args:
        state: Current state
        tool_name: Name of the tool called
        tool_args: Tool arguments
        tool_result: Tool result
        
    Returns:
        Updated state
    """
    state["tool_calls"].append({
        "tool": tool_name,
        "arguments": tool_args,
        "result": tool_result,
        "timestamp": datetime.now().isoformat()
    })
    return state


def should_create_ticket(state: ConversationState) -> bool:
    """
    Determine if a ticket should be created.
    
    Args:
        state: Current state
        
    Returns:
        True if ticket should be created
    """
    # Create ticket if:
    # 1. Customer identified
    # 2. Problem identified
    # 3. Troubleshooting attempted but not resolved
    # 4. OR requires escalation
    
    return (
        state["customer_identified"] and
        state["problem_identified"] and
        (
            (state["troubleshooting_attempted"] and not state["troubleshooting"]["resolved"]) or
            state["requires_escalation"]
        ) and
        not state["ticket_created"]
    )


def is_conversation_complete(state: ConversationState) -> bool:
    """
    Check if conversation can be ended.
    
    Args:
        state: Current state
        
    Returns:
        True if conversation is complete
    """
    # Conversation complete if:
    # 1. Problem resolved, OR
    # 2. Ticket created, OR
    # 3. Explicitly ended
    
    return (
        state["troubleshooting"].get("resolved", False) or
        state["ticket_created"] or
        state["conversation_ended"]
    )