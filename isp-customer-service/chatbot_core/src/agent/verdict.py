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
    gather_signals(db, customer_id) -> signals dict   (adapters, I/O)
    decide(signals)                 -> verdict dict   (pure function)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Sustained CRC errors above this rate (errors/min) indicate a damaged or
# poorly seated cable (B5) even while the link stays up.
CRC_ERROR_THRESHOLD = 1.0


# =============================================================================
# SIGNAL GATHERING (I/O — talks to the CRM and network adapters)
# =============================================================================


def gather_signals(db, customer_id: str) -> dict[str, Any]:
    """
    Collect the verdict's input signals from both services.

    Orchestrates CRM (billing) and network (outage / switch / port / telemetry
    / neighbours) — the two domains stay separate (no cross-schema JOINs), so
    swapping either backing for a real system later touches only the adapter.

    Returns a flat signals dict; on a hard failure returns
    {"error": ..., "message": ...} instead.
    """
    from crm_mcp.tools.customer_lookup import get_billing_status
    from network_diagnostic_mcp.tools.outage_checks import check_customer_affected_by_outage
    from network_diagnostic_mcp.tools.port_diagnostics import (
        check_port_status,
        get_switch_neighbor_summary,
    )

    # --- Step 1 signal: billing (CRM domain) -------------------------------
    billing = get_billing_status(db, customer_id)
    if not billing.get("success"):
        return {
            "error": billing.get("error", "billing_check_failed"),
            "message": billing.get("message", "Nepavyko patikrinti apmokėjimo būsenos."),
        }

    # --- Step 2 signal: registered incident (network domain) ---------------
    outage = check_customer_affected_by_outage(db, customer_id)
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
    port_result = check_port_status(db, customer_id)
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
        "incident": outage_info,
        "switch_status": port.get("switch_status") if port else None,
        "port_link": port.get("status") if port else None,
        "registered_mac": (
            port.get("connected_equipment", {}).get("mac_address") if port else None
        ),
        "observed_mac": port.get("observed_mac") if port else None,
        "crc_error_rate": port.get("crc_error_rate") if port else None,
        "dhcp_status": port.get("dhcp_status") if port else None,
        "neighbors_up": None,
        "neighbors_down": None,
    }

    # Neighbour correlation only matters when the customer's link is down
    # (BŪSENA A: local fault vs unregistered node fault).
    if port and port.get("status") != "up":
        neighbors = get_switch_neighbor_summary(
            db, port["switch_id"], exclude_customer_id=customer_id
        )
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
        reason_txt = signals.get("suspension_reason") or "neapmokėta sąskaita"
        return _verdict(
            side="provider",
            group="B1",
            action="inform",
            reason="billing_suspended",
            agent_message=(
                f"Paslauga sustabdyta dėl apmokėjimo ({reason_txt}). "
                "Informuok klientą, kaip apmokėti ir atstatyti paslaugą. "
                "Diagnostikos nereikia, tiketo nekurti."
            ),
        )

    # ---- Step 2: registered incident (B2) ----------------------------------
    incident = signals.get("incident")
    if incident:
        eta = incident.get("estimated_resolution")
        eta_txt = f" Numatomas atstatymas: {eta}." if eta else ""
        return _verdict(
            side="provider",
            group="B2",
            action="inform",
            reason="active_outage",
            agent_message=(
                f"Kliento rajone registruota avarija: {incident.get('description', '')}."
                f"{eta_txt} Informuok ir užbaik — avarija jau registruota, tiketo nekurti."
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
                "Nerasti kliento porto duomenys — diagnostika iš tiekėjo pusės negalima. "
                "Tęsk pokalbiu: ar dega routerio lemputės, ar įjungtas maitinimas."
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
                "Kliento tinklo mazgas nepasiekiamas, registruotos avarijos nėra — "
                "tiekėjo gedimas. Kurk tiketą; darbuotojas susisieks suderinti laiko."
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
                    "Kliento ir kaimynų portai neaktyvūs, bet avarija neregistruota — "
                    "tikėtinas mazgo gedimas. Kurk tiketą."
                ),
            )
        return _verdict(
            side="customer",
            group="B4/B5",
            action="instruct",
            reason="link_down_local",
            agent_message=(
                "Porto ryšys nutrūkęs, kaimynai veikia — gedimas kliento pusėje "
                "(maitinimas / laidai). Instruktuok pažingsniui: ar dega lemputės, "
                "ar gerai įkištas WAN laidas. Nepadėjus — tiketas."
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
                "Linija veikia, bet įrenginio nesimato — routeris greičiausiai "
                "išjungtas arba neprijungtas. Tikslink pokalbiu: maitinimas, laidai."
            ),
        )
    if registered and observed != registered:
        return _verdict(
            side="customer",
            group="B6",
            action="instruct",
            reason="foreign_mac",
            agent_message=(
                "Linijoje matomas kitas įrenginys nei registruota — klientas "
                "tikriausiai pakeitė routerį. Patvirtinus, atnaujink MAC "
                "(update_mac) ir perkrauk portą."
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
                "Linijoje daug CRC klaidų — pažeistas arba blogai įkištas laidas. "
                "Instruktuok patikrinti/perjungti laidą; nepadėjus — tiketas dėl "
                "laido keitimo."
            ),
        )
    if signals.get("dhcp_status") in ("no_requests", "expired"):
        return _verdict(
            side="customer",
            group="B6",
            action="instruct",
            reason="dhcp_silent",
            agent_message=(
                "Routeris matomas, bet nesiunčia DHCP užklausų — tikėtinas Factory "
                "Reset ar išsitrynusi konfigūracija. Instruktuok nustatyti DHCP "
                "routerio valdymo skydelyje."
            ),
        )

    # ---- Everything healthy up to the router --------------------------------
    return _verdict(
        side="unclear",
        group="B7",
        action="instruct",
        reason="healthy_to_router",
        agent_message=(
            "Tinklas iki routerio veikia — problema toliau kliento pusėje "
            "(Wi-Fi, įrenginys). Tikslink: ar neveikia visuose įrenginiuose, "
            "ar tik viename; laidu ar per Wi-Fi."
        ),
    )


# =============================================================================
# COMPOSITE (the tool body)
# =============================================================================


def diagnose(db, customer_id: str) -> dict[str, Any]:
    """gather_signals + decide -> the diagnose_connection tool payload."""
    signals = gather_signals(db, customer_id)
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
