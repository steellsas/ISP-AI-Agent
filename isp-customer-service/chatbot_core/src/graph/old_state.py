"""
Conversation State Schema
Defines the structure of conversation state used throughout the LangGraph workflow
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal, Annotated
from datetime import datetime
from langgraph.graph import add_messages 



def append_messages(left: List[Dict], right: List[Dict]) -> List[Dict]:
    """
    Custom reducer that appends messages (dict format).
    
    This is simpler than LangChain's add_messages and keeps dicts.
    """
    if not isinstance(left, list):
        left = []
    if not isinstance(right, list):
        right = []
    return left + right


class Message(TypedDict):
    """Single message in conversation."""
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str
    node: Optional[str]


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


class PhoneInfoMatch(TypedDict, total=False):
    """Single customer match from phone lookup."""
    customer_id: str
    name: str
    first_name: str
    last_name: str
    addresses: List[Dict[str, Any]]


class PhoneInfo(TypedDict):
    """Background phone lookup information (informational only)."""
    lookup_performed: bool
    found: bool
    phone_number: Optional[str]
    possible_matches: List[PhoneInfoMatch]


class ProblemInfo(TypedDict, total=False):
    """Problem identification information."""
    problem_type: Optional[Literal["internet", "tv", "phone", "other"]]
    category: Optional[str]
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
    
    # Provider issue flags
    provider_issue: bool
    issue_type: Optional[str]  # "outage", "maintenance", "line_problem"
    estimated_fix_time: Optional[str]


class TroubleshootingInfo(TypedDict, total=False):
    """Troubleshooting steps and results."""
    steps_taken: List[str]
    current_step: Optional[str]
    instructions_given: List[str]
    customer_actions: List[str]
    resolved: bool
    
    # Retry tracking
    retry_count: int
    max_retries: int
    last_solution_attempted: Optional[str]


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
    
    Key State Flow:
    1. phone_info: Background lookup results (informational only)
    2. customer_id: Set ONLY after address is confirmed
    3. confirmed_address_id: The specific address with the problem
    """
    
    # Conversation metadata
    conversation_id: str
    session_start: str
    language: Literal["lt", "en"]
    current_node: str
    
    # Messages history with reducer for proper checkpointing!
    # messages: Annotated[List[Message], add_messages]  # ← CRITICAL FIX!

    messages: Annotated[List[Message], append_messages]
    
    # === BACKGROUND PHONE LOOKUP (Informational Only) ===
    phone_info: PhoneInfo
    
    # === CONFIRMED CUSTOMER (Set ONLY after address verification) ===
    customer_id: Optional[str]  # ← Set after address confirmed
    confirmed_address_id: Optional[str]  # ← The address with problem
    
    # === FULL CUSTOMER DATA (Loaded after confirmation) ===
    customer: CustomerInfo
    customer_identified: bool  # ← Legacy flag, use customer_id instead
    
    # Address workflow
    address_confirmed: bool  # ← User confirmed the suggested address
    address_search_asked: bool  # ← Asked user for address input
    address_search_successful: bool  # ← Found by address lookup
    
    # Authentication (optional security check)
    authentication_required: bool
    authenticated: bool
    
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
    next_action: Optional[str]
    requires_escalation: bool
    conversation_ended: bool
    waiting_for_user_input: bool
    last_question: Optional[str]
    
    # RAG context
    retrieved_documents: List[Dict[str, Any]]
    
    # MCP tool calls history
    tool_calls: List[Dict[str, Any]]
    
    # Error tracking
    errors: List[Dict[str, Any]]
    last_error: Optional[str]
    
    # Additional context
    metadata: Dict[str, Any]


def create_initial_state(
    conversation_id: str,
    phone_number: Optional[str] = None,
    language: str = "lt"
) -> ConversationState:
    """
    Create initial conversation state.
    
    Args:
        conversation_id: Unique conversation identifier
        phone_number: Phone number from telephony (optional)
        language: Language code (lt or en)
        
    Returns:
        Initial state
    """
    
    customer_info = CustomerInfo()
    if phone_number:
        customer_info["phone"] = phone_number
    
    return ConversationState(
        conversation_id=conversation_id,
        session_start=datetime.now().isoformat(),
        language=language,
        # current_node="greeting",
        messages=[],
        
        # Phone info (empty initially)
        phone_info=PhoneInfo(
            lookup_performed=False,
            found=False,
            phone_number=phone_number,
            possible_matches=[]
        ),
        
        # Confirmed customer (None until address verified)
        customer_id=None,
        confirmed_address_id=None,
        
        # Full customer data
        customer=customer_info,
        customer_identified=False,
        
        # Address workflow
        address_confirmed=False,
        address_search_asked=False,
        address_search_successful=False,
        
        # Authentication
        authentication_required=False,
        authenticated=False,
        
        # Problem
        problem=ProblemInfo(),
        problem_identified=False,
        
        # Diagnostics
        diagnostics=DiagnosticResults(provider_issue=False),
        diagnostics_completed=False,
        
        # Troubleshooting
        troubleshooting=TroubleshootingInfo(
            steps_taken=[],
            instructions_given=[],
            customer_actions=[],
            resolved=False,
            retry_count=0,
            max_retries=3
        ),
        troubleshooting_attempted=False,
        
        # Ticket
        ticket=TicketInfo(created=False),
        ticket_created=False,
        
        # Workflow control
        next_action=None,
        requires_escalation=False,
        conversation_ended=False,
        waiting_for_user_input=False,
        last_question=None,
        
        # Context
        retrieved_documents=[],
        tool_calls=[],
        
        # Errors
        errors=[],
        last_error=None,
        
        # Metadata
        metadata={}
    )


def add_message(
    state: ConversationState,
    role: Literal["user", "assistant", "system"],
    content: str,
    node: Optional[str] = None
) -> ConversationState:
    """Add a message to conversation history."""
    message: Message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "node": node
    }
    state["messages"].append(message)
    return state


def get_last_user_message(state: ConversationState) -> Optional[str]:
    """Get the last user message."""
    user_messages = [msg for msg in state["messages"] if msg["role"] == "user"]
    if user_messages:
        return user_messages[-1]["content"]
    return None


def get_conversation_history(
    state: ConversationState,
    max_messages: int = 10
) -> List[Message]:
    """
    Get recent conversation history.
    
    Args:
        state: Current state
        max_messages: Maximum number of messages to return
        
    Returns:
        List of recent messages
    """
    return state["messages"][-max_messages:]


def add_tool_call(
    state: ConversationState,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_output: Any,
    node: str
) -> ConversationState:
    """Record a tool call."""
    state["tool_calls"].append({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "node": node,
        "timestamp": datetime.now().isoformat()
    })
    return state


def add_error(
    state: ConversationState,
    error_message: str,
    node: str,
    error_type: str = "general"
) -> ConversationState:
    """Record an error."""
    error = {
        "message": error_message,
        "node": node,
        "type": error_type,
        "timestamp": datetime.now().isoformat()
    }
    state["errors"].append(error)
    state["last_error"] = error_message
    return state


# === HELPER FUNCTIONS FOR NEW WORKFLOW ===

def set_confirmed_customer(
    state: ConversationState,
    customer_id: str,
    address_id: str
) -> ConversationState:
    """
    Set confirmed customer and address after verification.
    This is the ONLY way customer_id should be set.
    
    Args:
        state: Current state
        customer_id: Confirmed customer ID
        address_id: Confirmed address ID
        
    Returns:
        Updated state
    """
    state["customer_id"] = customer_id
    state["confirmed_address_id"] = address_id
    state["customer_identified"] = True  # Legacy flag
    return state


def get_phone_info_addresses(state: ConversationState) -> List[Dict[str, Any]]:
    """
    Get addresses from phone_info if available.
    
    Args:
        state: Current state
        
    Returns:
        List of addresses or empty list
    """
    phone_info = state.get("phone_info", {})
    if not phone_info.get("found"):
        return []
    
    matches = phone_info.get("possible_matches", [])
    if not matches:
        return []
    
    # Return addresses from first match
    return matches[0].get("addresses", [])


def is_customer_confirmed(state: ConversationState) -> bool:
    """
    Check if customer has been confirmed.
    
    Returns:
        True if customer_id is set
    """
    return state.get("customer_id") is not None