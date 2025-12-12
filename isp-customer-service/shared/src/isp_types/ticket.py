"""
Ticket-related Pydantic models.
"""

from datetime import datetime
from typing import Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field


class TicketType(str, Enum):
    """Ticket type enumeration."""

    NETWORK_ISSUE = "network_issue"
    RESOLVED = "resolved"
    TECHNICIAN_VISIT = "technician_visit"
    CUSTOMER_NOT_FOUND = "customer_not_found"
    NO_SERVICE_AREA = "no_service_area"


class TicketPriority(str, Enum):
    """Ticket priority enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    """Ticket status enumeration."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class Ticket(BaseModel):
    """Support ticket model."""

    ticket_id: str = Field(..., description="Unique ticket ID")
    customer_id: str = Field(..., description="Customer ID")
    ticket_type: TicketType = Field(..., description="Ticket type")
    problem_type: Optional[str] = Field(None, description="Problem category")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Ticket priority")
    status: TicketStatus = Field(default=TicketStatus.OPEN, description="Ticket status")
    summary: str = Field(..., description="Brief summary")
    details: Optional[str] = Field(None, description="Detailed description")
    resolution_summary: Optional[str] = Field(None, description="Resolution summary")
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Updated timestamp")
    resolved_at: Optional[datetime] = Field(None, description="Resolved timestamp")
    assigned_to: Optional[str] = Field(None, description="Assigned technician")
    troubleshooting_steps: Optional[str] = Field(None, description="Steps taken to troubleshoot")

    class Config:
        from_attributes = True
        use_enum_values = True

    def is_open(self) -> bool:
        """Check if ticket is open."""
        return self.status in [TicketStatus.OPEN, TicketStatus.IN_PROGRESS]

    def is_resolved(self) -> bool:
        """Check if ticket is resolved."""
        return self.status == TicketStatus.CLOSED and self.resolved_at is not None


class TicketCreateRequest(BaseModel):
    """Request model for creating a new ticket."""

    customer_id: str = Field(..., description="Customer ID")
    ticket_type: TicketType = Field(..., description="Ticket type")
    problem_type: Optional[str] = Field(None, description="Problem category")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Ticket priority")
    summary: str = Field(..., description="Brief summary")
    details: Optional[str] = Field(None, description="Detailed description")
    troubleshooting_steps: Optional[str] = Field(None, description="Steps already taken")


class TicketUpdateRequest(BaseModel):
    """Request model for updating a ticket."""

    status: Optional[TicketStatus] = Field(None, description="New status")
    priority: Optional[TicketPriority] = Field(None, description="New priority")
    details: Optional[str] = Field(None, description="Additional details")
    resolution_summary: Optional[str] = Field(None, description="Resolution summary")
    assigned_to: Optional[str] = Field(None, description="Assigned technician")
    troubleshooting_steps: Optional[str] = Field(
        None, description="Additional troubleshooting steps"
    )
