"""
Network-related Pydantic models.
"""

from datetime import datetime
from typing import Optional, Literal
from enum import Enum
from decimal import Decimal
from pydantic import BaseModel, Field


class PortStatus(str, Enum):
    """Port status enumeration."""

    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "admin_down"
    ERROR = "error"


class Switch(BaseModel):
    """Network switch model."""

    switch_id: str = Field(..., description="Unique switch ID")
    switch_name: str = Field(..., description="Switch name")
    location: str = Field(..., description="Physical location")
    ip_address: Optional[str] = Field(None, description="Management IP address")
    model: Optional[str] = Field(None, description="Switch model")
    status: Literal["active", "inactive", "maintenance"] = Field(
        default="active", description="Switch status"
    )
    max_ports: int = Field(default=48, description="Maximum number of ports")
    created_at: datetime = Field(default_factory=datetime.now, description="Created timestamp")
    last_checked: datetime = Field(default_factory=datetime.now, description="Last health check")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True


class Port(BaseModel):
    """Network port model."""

    port_id: str = Field(..., description="Unique port ID")
    switch_id: str = Field(..., description="Switch ID")
    port_number: int = Field(..., description="Port number")
    customer_id: Optional[str] = Field(None, description="Connected customer ID")
    equipment_mac: Optional[str] = Field(None, description="Connected equipment MAC")
    status: PortStatus = Field(default=PortStatus.DOWN, description="Port status")
    speed_mbps: Optional[int] = Field(None, description="Port speed in Mbps")
    duplex: Optional[Literal["full", "half", "auto"]] = Field(None, description="Duplex mode")
    vlan_id: Optional[int] = Field(None, description="VLAN ID")
    last_status_change: datetime = Field(
        default_factory=datetime.now, description="Last status change"
    )
    last_checked: datetime = Field(default_factory=datetime.now, description="Last check")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True
        use_enum_values = True

    def is_active(self) -> bool:
        """Check if port is active (up)."""
        return self.status == PortStatus.UP

    def is_assigned(self) -> bool:
        """Check if port is assigned to a customer."""
        return self.customer_id is not None


class IPAssignment(BaseModel):
    """IP address assignment model."""

    assignment_id: str = Field(..., description="Unique assignment ID")
    customer_id: Optional[str] = Field(None, description="Customer ID")
    ip_address: str = Field(..., description="Assigned IP address")
    mac_address: Optional[str] = Field(None, description="MAC address")
    assignment_type: Optional[Literal["static", "dhcp", "pppoe"]] = Field(
        None, description="Assignment type"
    )
    assigned_at: datetime = Field(default_factory=datetime.now, description="Assigned timestamp")
    lease_expires: Optional[datetime] = Field(None, description="DHCP lease expiration")
    status: Literal["active", "expired", "reserved", "blacklisted"] = Field(
        default="active", description="Assignment status"
    )
    last_seen: datetime = Field(default_factory=datetime.now, description="Last seen online")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True


class AreaOutage(BaseModel):
    """Area-wide outage model."""

    outage_id: str = Field(..., description="Unique outage ID")
    city: str = Field(..., description="Affected city")
    street: Optional[str] = Field(None, description="Affected street")
    area_description: Optional[str] = Field(None, description="Area description")
    outage_type: Literal["internet", "tv", "phone", "all"] = Field(
        ..., description="Service type affected"
    )
    severity: Literal["minor", "major", "critical"] = Field(
        default="major", description="Outage severity"
    )
    status: Literal["active", "resolved", "investigating"] = Field(
        default="active", description="Outage status"
    )
    reported_at: datetime = Field(default_factory=datetime.now, description="Reported timestamp")
    resolved_at: Optional[datetime] = Field(None, description="Resolved timestamp")
    estimated_resolution: Optional[datetime] = Field(None, description="Estimated resolution time")
    affected_customers: Optional[int] = Field(None, description="Number of affected customers")
    description: str = Field(..., description="Outage description")
    root_cause: Optional[str] = Field(None, description="Root cause")
    resolution_notes: Optional[str] = Field(None, description="Resolution notes")

    class Config:
        from_attributes = True

    def is_active(self) -> bool:
        """Check if outage is active."""
        return self.status == "active"

    def affects_service(self, service_type: str) -> bool:
        """Check if outage affects specific service type."""
        return self.outage_type in [service_type, "all"]


class BandwidthLog(BaseModel):
    """Bandwidth measurement log model."""

    log_id: str = Field(..., description="Unique log ID")
    customer_id: str = Field(..., description="Customer ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Measurement timestamp")
    download_mbps: Optional[Decimal] = Field(None, description="Download speed in Mbps")
    upload_mbps: Optional[Decimal] = Field(None, description="Upload speed in Mbps")
    latency_ms: Optional[int] = Field(None, description="Latency in milliseconds")
    packet_loss_percent: Optional[Decimal] = Field(None, description="Packet loss percentage")
    jitter_ms: Optional[Decimal] = Field(None, description="Jitter in milliseconds")
    measurement_type: Optional[Literal["speedtest", "continuous", "diagnostic"]] = Field(
        None, description="Measurement type"
    )
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True


class SignalQuality(BaseModel):
    """Signal quality measurement model (for TV/Cable)."""

    quality_id: str = Field(..., description="Unique quality ID")
    customer_id: str = Field(..., description="Customer ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Measurement timestamp")
    signal_strength_dbm: Optional[int] = Field(None, description="Signal strength in dBm")
    snr_db: Optional[Decimal] = Field(None, description="Signal-to-noise ratio in dB")
    ber: Optional[Decimal] = Field(None, description="Bit error rate")
    mer_db: Optional[Decimal] = Field(None, description="Modulation error ratio in dB")
    status: Optional[Literal["excellent", "good", "fair", "poor", "critical"]] = Field(
        None, description="Quality status"
    )
    channel_issues: Optional[str] = Field(None, description="Channel-specific issues")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True
