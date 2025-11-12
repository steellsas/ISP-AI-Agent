"""Shared Pydantic types and models."""

from .customer import (
    Customer,
    Address,
    ServicePlan,
    CustomerEquipment,
    CustomerMemory,
)
from .ticket import (
    Ticket,
    TicketType,
    TicketPriority,
    TicketStatus,
)
from .network import (
    Switch,
    Port,
    PortStatus,
    IPAssignment,
    AreaOutage,
    BandwidthLog,
)

__all__ = [
    # Customer types
    "Customer",
    "Address",
    "ServicePlan",
    "CustomerEquipment",
    "CustomerMemory",
    # Ticket types
    "Ticket",
    "TicketType",
    "TicketPriority",
    "TicketStatus",
    # Network types
    "Switch",
    "Port",
    "PortStatus",
    "IPAssignment",
    "AreaOutage",
    "BandwidthLog",
]