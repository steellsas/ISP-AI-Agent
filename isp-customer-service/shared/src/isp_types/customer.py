"""
Customer-related Pydantic models.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Customer(BaseModel):
    """Customer model."""

    customer_id: str = Field(..., description="Unique customer ID")
    first_name: str = Field(..., description="Customer first name")
    last_name: str = Field(..., description="Customer last name")
    phone: str | None = Field(None, description="Phone number")
    email: str | None = Field(None, description="Email address")
    status: Literal["active", "suspended", "cancelled"] = Field(
        default="active", description="Customer status"
    )
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")
    notes: str | None = Field(None, description="Additional notes")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format."""
        if v and not v.startswith("+"):
            raise ValueError("Phone must start with country code (+)")
        return v


class Address(BaseModel):
    """Customer address model."""

    address_id: str = Field(..., description="Unique address ID")
    customer_id: str = Field(..., description="Customer ID")
    city: str = Field(..., description="City name")
    street: str = Field(..., description="Street name")
    house_number: str = Field(..., description="House number")
    apartment_number: str | None = Field(None, description="Apartment number")
    postal_code: str | None = Field(None, description="Postal code")
    full_address: str | None = Field(None, description="Full formatted address")
    is_primary: bool = Field(default=True, description="Is primary address")
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")

    model_config = ConfigDict(from_attributes=True)

    def format_address(self) -> str:
        """Format address as human-readable string."""
        parts = [self.city, self.street, self.house_number]
        if self.apartment_number:
            parts.append(f"-{self.apartment_number}")
        return ", ".join(filter(None, parts))


class ServicePlan(BaseModel):
    """Service plan model."""

    plan_id: str = Field(..., description="Unique plan ID")
    customer_id: str = Field(..., description="Customer ID")
    service_type: Literal["internet", "tv", "phone", "bundle"] = Field(
        ..., description="Service type"
    )
    plan_name: str = Field(..., description="Plan name")
    speed_mbps: int | None = Field(None, description="Internet speed in Mbps")
    price: float = Field(..., description="Monthly price")
    status: Literal["active", "suspended", "cancelled"] = Field(
        default="active", description="Plan status"
    )
    activation_date: date = Field(..., description="Activation date")
    suspension_reason: str | None = Field(None, description="Suspension reason")
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        """Validate price is positive."""
        if v < 0:
            raise ValueError("Price must be positive")
        return v


class CustomerEquipment(BaseModel):
    """Customer equipment model."""

    equipment_id: str = Field(..., description="Unique equipment ID")
    customer_id: str = Field(..., description="Customer ID")
    equipment_type: Literal["router", "modem", "decoder", "phone", "ont"] = Field(
        ..., description="Equipment type"
    )
    model: str | None = Field(None, description="Equipment model")
    serial_number: str | None = Field(None, description="Serial number")
    mac_address: str | None = Field(None, description="MAC address")
    installed_date: date | None = Field(None, description="Installation date")
    status: Literal["active", "inactive", "faulty", "returned"] = Field(
        default="active", description="Equipment status"
    )
    notes: str | None = Field(None, description="Additional notes")
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")

    model_config = ConfigDict(from_attributes=True)


class CustomerMemory(BaseModel):
    """Customer memory/preferences model."""

    memory_id: str = Field(..., description="Unique memory ID")
    customer_id: str = Field(..., description="Customer ID")
    memory_key: str = Field(..., description="Memory key")
    memory_value: str | None = Field(None, description="Memory value")
    last_updated: datetime = Field(default_factory=datetime.now, description="Last updated")

    model_config = ConfigDict(from_attributes=True)


class CustomerHistory(BaseModel):
    """Customer history event model."""

    history_id: str = Field(..., description="Unique history ID")
    customer_id: str = Field(..., description="Customer ID")
    event_type: Literal[
        "ticket_created",
        "ticket_resolved",
        "payment",
        "service_change",
        "equipment_change",
        "status_change",
    ] = Field(..., description="Event type")
    event_date: datetime = Field(default_factory=datetime.now, description="Event date")
    details: str | None = Field(None, description="Event details")
    related_ticket_id: str | None = Field(None, description="Related ticket ID")

    model_config = ConfigDict(from_attributes=True)
