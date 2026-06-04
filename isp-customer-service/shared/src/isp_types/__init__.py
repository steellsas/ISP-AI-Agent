"""Shared Pydantic types and models."""

from .customer import (
    Address,
    Customer,
    CustomerEquipment,
    CustomerMemory,
    ServicePlan,
)
from .network import (
    AreaOutage,
    BandwidthLog,
    IPAssignment,
    Port,
    PortStatus,
    Switch,
)
from .ticket import (
    Ticket,
    TicketPriority,
    TicketStatus,
    TicketType,
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
