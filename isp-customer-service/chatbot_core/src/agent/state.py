"""
Agent State Management.

Contains the state dataclass that tracks conversation progress.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class AgentState:
    """
    Agent conversation state.
    
    Tracks all information gathered during a customer support call.
    """
    # Call identification
    caller_phone: str
    
    # Conversation history (for LLM context)
    messages: List[Dict[str, str]] = field(default_factory=list)
    
    # Customer information (populated after find_customer)
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None  # Name from CRM (may differ from caller)
    customer_address: Optional[str] = None
    
    # Caller information (populated after customer confirms)
    caller_name: Optional[str] = None  # Actual caller's name
    address_confirmed: bool = False
    
    # Tool observations
    observations: List[str] = field(default_factory=list)
    
    # Problem tracking
    problem_type: Optional[str] = None  # internet, tv, phone, billing
    problem_description: Optional[str] = None
    
    # Conversation control
    is_complete: bool = False
    turn_count: int = 0
    max_turns: int = 20
    
    # Ticket info (if created)
    ticket_id: Optional[str] = None
    
    def add_observation(self, observation: str):
        """Add tool observation to history."""
        self.observations.append(observation)
    
    def set_customer_info(self, customer_id: str, name: str = None, address: str = None):
        """Set customer information from CRM lookup."""
        self.customer_id = customer_id
        self.customer_name = name
        self.customer_address = address
    
    def confirm_address(self, caller_name: str = None):
        """Mark address as confirmed by caller."""
        self.address_confirmed = True
        if caller_name:
            self.caller_name = caller_name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "caller_phone": self.caller_phone,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "caller_name": self.caller_name,
            "address_confirmed": self.address_confirmed,
            "problem_type": self.problem_type,
            "problem_description": self.problem_description,
            "is_complete": self.is_complete,
            "turn_count": self.turn_count,
            "ticket_id": self.ticket_id,
        }
