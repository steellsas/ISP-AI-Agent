"""diagnose_connection — one provider-side READING of the line.

It gathers every signal the engine can see (billing, a registered incident, the switch, the
port, the neighbours) in ONE call, and returns them. What they MEAN is not decided here: the
signals become facts (knowledge/signals.yaml) and the fault cards declare which fault those
facts allow (wave 3), including the news cards for a debt, an outage or a node down (wave 4).

Until then this module held the decision tree from docs/scenarijus_neveikia_internetas.md
§3.2 — twelve verdicts, and a new situation meant a new branch in Python.

The sources (CRM billing, network outage/port/neighbours) are supplied by the tool provider;
this module imports no adapter.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from .contract import limits

logger = logging.getLogger(__name__)


def _flap_recent(last_status_change: str | None, window_s: int | None = None) -> bool:
    """True when the port's last status change is within the reboot window
    (`reboot_flap_window_s`): a real reboot drops the device off the line, so
    last_status_change refreshes; a stale stamp means the wrong device (a second
    router) or just the extension cord was power-cycled.
    SQLite CURRENT_TIMESTAMP / datetime('now') stamps are UTC 'YYYY-MM-DD HH:MM:SS'."""
    if not last_status_change:
        return False
    try:
        ts = datetime.fromisoformat(str(last_status_change)).replace(tzinfo=UTC)
    except ValueError:
        return False
    if window_s is None:
        window_s = limits.get("reboot_flap_window_s")
    return (datetime.now(UTC) - ts).total_seconds() <= window_s


# =============================================================================
# SIGNAL GATHERING (I/O — talks to the CRM and network adapters)
# =============================================================================


class TelemetrySources(Protocol):
    """The CRM and network reads the verdict needs (one call's worth)."""

    def billing_status(self, customer_id: str) -> dict[str, Any]: ...

    def outage_for_customer(self, customer_id: str) -> dict[str, Any]: ...

    def port_status(self, customer_id: str) -> dict[str, Any]: ...

    def switch_neighbors(self, switch_id: str, exclude_customer_id: str) -> dict[str, Any]: ...


def gather_signals(sources: TelemetrySources, customer_id: str) -> dict[str, Any]:
    """
    Collect the verdict's input signals from both services.

    Orchestrates CRM (billing) and network (outage / switch / port / telemetry
    / neighbours) — the two domains stay separate (no cross-schema JOINs), so
    swapping either backing for a real system later touches only the sources.

    Returns a flat signals dict; on a hard failure returns
    {"error": ..., "message": ...} instead.
    """
    # --- Step 1 signal: billing (CRM domain) -------------------------------
    billing = sources.billing_status(customer_id)
    if not billing.get("success"):
        return {
            "error": billing.get("error", "billing_check_failed"),
            "message": billing.get("message", "Could not check the billing status."),
        }

    # --- Step 2 signal: registered incident (network domain) ---------------
    outage = sources.outage_for_customer(customer_id)
    outage_info = None
    if outage.get("success") and outage.get("affected"):
        first = (outage.get("outages") or [{}])[0]
        outage_info = {
            "outage_id": first.get("outage_id"),
            "description": first.get("description"),
            "estimated_resolution": first.get("estimated_resolution"),
            "severity": first.get("severity"),
        }

    # --- Steps 3-4 signals: switch + port + telemetry ----------------------
    port_result = sources.port_status(customer_id)
    port = None
    if port_result.get("success") and port_result.get("ports"):
        ports = port_result["ports"]
        # Diagnose the router/internet port: prefer the port whose connected
        # equipment is the router (a TV decoder port would mislead the tree).
        port = next(
            (
                p
                for p in ports
                if p.get("connected_equipment", {}).get("equipment_type") == "router"
            ),
            ports[0],
        )

    signals: dict[str, Any] = {
        "customer_id": customer_id,
        "billing_suspended": billing.get("suspended", False),
        "suspension_reason": next(
            (p.get("suspension_reason") for p in billing.get("suspended_plans", [])), None
        ),
        # Closing wave (2026-09-08): debt details for the inform template
        # ({amount, months, last_payment} or None on an older DB).
        "billing_debt": billing.get("debt"),
        "incident": outage_info,
        "switch_status": port.get("switch_status") if port else None,
        "port_link": port.get("status") if port else None,
        "registered_mac": (
            port.get("connected_equipment", {}).get("mac_address") if port else None
        ),
        # What the CRM says the caller HAS (wave 3e): the equipment catalogue picks the
        # instruction from the model, its family, or the basic device — in that order.
        "device_type": (
            port.get("connected_equipment", {}).get("equipment_type") if port else None
        ),
        "device_model": port.get("connected_equipment", {}).get("model") if port else None,
        "observed_mac": port.get("observed_mac") if port else None,
        "crc_error_rate": port.get("crc_error_rate") if port else None,
        "dhcp_status": port.get("dhcp_status") if port else None,
        "traffic": port.get("traffic_status") if port else None,
        "port_flap_recent": _flap_recent(port.get("last_status_change")) if port else False,
        "neighbors_up": None,
        "neighbors_down": None,
    }

    # Neighbour correlation only matters when the customer's link is down
    # (STATE A: local fault vs unregistered node fault).
    if port and port.get("status") != "up":
        neighbors = sources.switch_neighbors(port["switch_id"], exclude_customer_id=customer_id)
        if neighbors.get("success"):
            signals["neighbors_up"] = neighbors["neighbors_up"]
            signals["neighbors_down"] = neighbors["neighbors_down"]

    return signals


# =============================================================================
# COMPOSITE (the tool body)
# =============================================================================


def diagnose(sources: TelemetrySources, customer_id: str) -> dict[str, Any]:
    """The diagnose_connection payload: what the line shows right now.

    `signals` is the whole reading; the engine turns it into facts and the cards decide. A
    failed reading returns its error instead, and the manifest's `on_failure` plan takes over
    (wave 2c).
    """
    signals = gather_signals(sources, customer_id)
    if "error" in signals:
        return {
            "success": False,
            "error": signals["error"],
            "message": signals.get("message", "Diagnostika nepavyko."),
        }
    logger.info(f"[DIAGNOSE] customer={customer_id} signals={len(signals)}")
    return {"success": True, "signals": signals}
