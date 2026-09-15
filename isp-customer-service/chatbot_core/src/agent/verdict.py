"""
diagnose_connection verdict — the "thick" deterministic diagnostic composite.

One call gathers all provider-side signals (billing, incident, switch, port
telemetry, neighbour correlation) and runs the decision tree from
docs/scenarijus_neveikia_internetas.md §3.2 (Steps 1-4, BŪSENA A/B/C). The
tree lives HERE in code — not in the prompt — so the provider/customer split
is fast and deterministic (voice-friendly: one tool call, no LLM reasoning
over raw telemetry).

The verdict draws the boundary but does NOT decide the final customer-side
cause: on side=customer/unclear the agent continues the conversation
(symptom questions + RAG instructions). See
docs/demo_plan_neveikia_internetas.md §2.

Split in two so the tree is unit-testable without a database:
    gather_signals(sources, customer_id) -> signals dict   (I/O through the sources)
    decide(signals)                      -> verdict dict   (pure function)

The sources (CRM billing, network outage/port/neighbours) are supplied by the
tool provider — this module imports no adapter.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Sustained CRC errors above this rate (errors/min) indicate a damaged or
# poorly seated cable (B5) even while the link stays up.
CRC_ERROR_THRESHOLD = 1.0

# A port status flap (down->up) within this window counts as "the router WAS
# power-cycled" (S6 hung router): a real reboot drops the device off the line,
# so last_status_change refreshes. "Perkroviau" with a stale timestamp means
# the wrong device (a second router) or just the extension cord was cycled.
REBOOT_FLAP_WINDOW_S = 600


def _flap_recent(last_status_change: str | None, window_s: int = REBOOT_FLAP_WINDOW_S) -> bool:
    """True when the port's last status change is within the reboot window.
    SQLite CURRENT_TIMESTAMP / datetime('now') stamps are UTC 'YYYY-MM-DD HH:MM:SS'."""
    if not last_status_change:
        return False
    try:
        ts = datetime.fromisoformat(str(last_status_change)).replace(tzinfo=UTC)
    except ValueError:
        return False
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
        "observed_mac": port.get("observed_mac") if port else None,
        "crc_error_rate": port.get("crc_error_rate") if port else None,
        "dhcp_status": port.get("dhcp_status") if port else None,
        "traffic": port.get("traffic_status") if port else None,
        "port_flap_recent": _flap_recent(port.get("last_status_change")) if port else False,
        "neighbors_up": None,
        "neighbors_down": None,
    }

    # Neighbour correlation only matters when the customer's link is down
    # (BŪSENA A: local fault vs unregistered node fault).
    if port and port.get("status") != "up":
        neighbors = sources.switch_neighbors(port["switch_id"], exclude_customer_id=customer_id)
        if neighbors.get("success"):
            signals["neighbors_up"] = neighbors["neighbors_up"]
            signals["neighbors_down"] = neighbors["neighbors_down"]

    return signals


# =============================================================================
# DECISION TREE (pure — no I/O, unit-testable)
# =============================================================================


def _verdict(side: str, group: str, action: str, reason: str, agent_message: str) -> dict:
    return {
        "side": side,  # provider | customer | unclear
        "group": group,  # B1..B7 resolution group (domain doc §2)
        "action": action,  # inform | create_ticket | instruct
        "reason": reason,
        "agent_message": agent_message,
    }


def decide(signals: dict[str, Any]) -> dict[str, Any]:
    """
    Run the decision tree over gathered signals (domain doc §3.2).

    Cheapest call-terminating checks first (billing, incident) — that IS the
    fast path of the two-speed flow: a B1/B2 verdict means inform-and-finish
    with no further diagnostics narrated to the customer.
    """
    # ---- Step 1: billing block (B1) ----------------------------------------
    if signals.get("billing_suspended"):
        reason_txt = signals.get("suspension_reason") or "unpaid invoice"
        return _verdict(
            side="provider",
            group="B1",
            action="inform",
            reason="billing_suspended",
            agent_message=(
                f"Service suspended for billing ({reason_txt}). "
                "Tell the caller how to pay and restore the service. "
                "No diagnostics needed, do not create a ticket."
            ),
        )

    # ---- Step 2: registered incident (B2) ----------------------------------
    incident = signals.get("incident")
    if incident:
        eta = incident.get("estimated_resolution")
        eta_txt = f" Estimated restoration: {eta}." if eta else ""
        return _verdict(
            side="provider",
            group="B2",
            action="inform",
            reason="active_outage",
            agent_message=(
                f"A registered outage in the caller's area: {incident.get('description', '')}."
                f"{eta_txt} Inform and finish — the outage is already registered, do not create a ticket."
            ),
        )

    # ---- No port data: cannot run steps 3-4 --------------------------------
    if signals.get("port_link") is None:
        return _verdict(
            side="unclear",
            group="B6",
            action="instruct",
            reason="no_port_data",
            agent_message=(
                "No port data for the caller — provider-side diagnostics are not possible. "
                "Continue in conversation: are the router lights on, is the power on."
            ),
        )

    # ---- Step 3: switch unreachable (B3) ------------------------------------
    if signals.get("switch_status") != "active":
        return _verdict(
            side="provider",
            group="B3",
            action="create_ticket",
            reason="switch_unreachable",
            agent_message=(
                "The caller's network node is unreachable, no outage is registered — "
                "a provider fault. INFORM the caller: a suspected fault in the NETWORK, they "
                "need to do nothing; once it is fixed, someone will contact them and "
                "report the repair. If they ask WHEN — promise no exact time: we will "
                "do it as fast as possible and let them know once it is "
                "fixed. The ticket was already created automatically."
            ),
        )

    # ---- Step 4, BŪSENA A: link DOWN ----------------------------------------
    if signals.get("port_link") != "up":
        neighbors_up = signals.get("neighbors_up")
        if neighbors_up == 0 and (signals.get("neighbors_down") or 0) > 0:
            return _verdict(
                side="provider",
                group="B3",
                action="create_ticket",
                reason="node_fault_unregistered",
                agent_message=(
                    "The caller's and the neighbours' ports are inactive, but no outage is registered — "
                    "a likely node fault. INFORM the caller: a suspected fault in the "
                    "NETWORK (not only at their place), they need to do nothing; once the fault "
                    "is fixed, someone will contact them and report the repair. "
                    "If they ask WHEN — promise no exact time: we will do it as "
                    "fast as possible and let them know once it is fixed. The ticket was "
                    "already created automatically."
                ),
            )
        return _verdict(
            side="customer",
            group="B4/B5",
            action="instruct",
            reason="link_down_local",
            agent_message=(
                "The port link is down, the neighbours work — a fault on the caller's side "
                "(power / cables). Instruct step by step: are the lights on, "
                "is the WAN cable seated well. If that does not help — a ticket."
            ),
        )

    # ---- Step 4, BŪSENA B: link UP, MAC missing or foreign ------------------
    observed = (signals.get("observed_mac") or "").lower() or None
    registered = (signals.get("registered_mac") or "").lower() or None
    if observed is None:
        return _verdict(
            side="unclear",
            group="B6",
            action="instruct",
            reason="no_mac_observed",
            agent_message=(
                "The line works, but no device is seen — the router is most likely "
                "off or not connected. Clarify in conversation: power, cables."
            ),
        )
    if registered and observed != registered:
        return _verdict(
            side="customer",
            group="B6",
            action="instruct",
            reason="foreign_mac",
            agent_message=(
                "A different device than registered is seen on the line — the caller "
                "probably changed the router. Once confirmed, update the MAC "
                "(update_mac) and reset the port."
            ),
        )

    # ---- Step 4, BŪSENA C: link UP, correct MAC -----------------------------
    crc = signals.get("crc_error_rate")
    if crc is not None and crc > CRC_ERROR_THRESHOLD:
        return _verdict(
            side="customer",
            group="B5",
            action="instruct",
            reason="crc_errors",
            agent_message=(
                "Many CRC errors on the line — a damaged or badly seated cable. "
                "Instruct to check/reconnect the cable; if that does not help — a ticket for "
                "a cable replacement."
            ),
        )
    if signals.get("dhcp_status") in ("no_requests", "expired"):
        return _verdict(
            side="customer",
            group="B6",
            action="instruct",
            reason="dhcp_silent",
            agent_message=(
                "The router is seen, but sends no DHCP requests — a likely factory "
                "reset or a wiped configuration. Instruct to set DHCP "
                "in the router's control panel."
            ),
        )

    # ---- Step 4, BŪSENA C tęsinys: device visible, DHCP fine, NO traffic ----
    # S6 "pakibęs routeris": everything up to the router looks alive, but no
    # frames flow — the router hung. A power-cycle usually clears it, so the
    # fix is an INSTRUCT (guided reboot), not a ticket. port_flap_recent is
    # the reboot witness the verify step reads afterwards.
    if signals.get("traffic") == "none":
        return _verdict(
            side="customer",
            group="B6",
            action="instruct",
            reason="router_hung",
            agent_message=(
                "The router is seen on the line, but no traffic flows — the router "
                "has most likely hung. Explain it humanly (it happens, a "
                "reboot usually clears it) and guide a power-cycle "
                "reboot. Do not create a ticket yet."
            ),
        )

    # ---- Everything healthy up to the router --------------------------------
    return _verdict(
        side="unclear",
        group="B7",
        action="instruct",
        reason="healthy_to_router",
        agent_message=(
            "The network works up to the router — the problem is further on the caller's side "
            "(Wi-Fi, a device). Clarify: does it fail on all devices "
            "or only one; wired or over Wi-Fi."
        ),
    )


# =============================================================================
# COMPOSITE (the tool body)
# =============================================================================


def diagnose(sources: TelemetrySources, customer_id: str) -> dict[str, Any]:
    """gather_signals + decide -> the diagnose_connection tool payload."""
    signals = gather_signals(sources, customer_id)
    if "error" in signals:
        return {
            "success": False,
            "error": signals["error"],
            "message": signals.get("message", "Diagnostika nepavyko."),
        }

    verdict = decide(signals)
    logger.info(
        f"[VERDICT] {customer_id}: side={verdict['side']} group={verdict['group']} "
        f"action={verdict['action']} reason={verdict['reason']}"
    )
    return {"success": True, "verdict": verdict, "signals": signals}
