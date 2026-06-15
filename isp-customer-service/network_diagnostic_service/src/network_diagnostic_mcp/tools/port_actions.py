"""
Port actions — SIMULATED remote operations (demo stubs with mock-DB effect).

Phase 2.5 step 5. In production these talk to provisioning (RADIUS / DHCP /
switch CLI); in the demo they mutate the seeded mock DB so the flow is
believable end-to-end: after bind_port_mac a repeated diagnose_connection
shows the problem GONE (observed == registered, DHCP ok) instead of the
agent merely claiming success.

Network-domain side only: the port binding and lease. The CRM equipment
registry update lives in the CRM adapter; the agent-level update_mac tool
orchestrates both (same pattern as diagnose_connection — no cross-schema
writes here).
"""

import sys
from pathlib import Path
from typing import Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger

from database import DatabaseConnection

logger = get_logger(__name__)


def bind_port_mac(db: DatabaseConnection, customer_id: str) -> dict[str, Any]:
    """
    SIMULATED: bind the MAC currently OBSERVED on the customer's port.

    The classic B6 "naujas routeris" fix: the customer connected a new device,
    the port sees its (foreign) MAC, we re-bind authorization to it. Also the
    core action of the B-Plan bridge (cable straight into a PC / customer's
    own router while waiting for the technician).

    Returns the old/new MAC so the agent can narrate what happened.
    """
    logger.info(f"[SIM] Binding observed MAC for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT port_id, equipment_mac, observed_mac, status
                FROM ports WHERE customer_id = ?
                """,
                (customer_id,),
            )
            port = cursor.fetchone()

        if not port:
            return {
                "success": False,
                "error": "no_port_found",
                "message": "Klientui nerastas tinklo portas.",
            }

        port = dict(port)
        observed = port.get("observed_mac")
        if not observed:
            return {
                "success": False,
                "error": "no_observed_mac",
                "message": (
                    "Linijoje šiuo metu nesimato jokio įrenginio — nėra ko pririšti. "
                    "Paprašykite kliento prijungti įrenginį (routerį/kompiuterį) prie "
                    "linijos ir pabandykite dar kartą."
                ),
            }

        old_mac = port.get("equipment_mac")

        with db.transaction() as cursor:
            # Re-bind the port authorization to the observed device...
            cursor.execute(
                """
                UPDATE ports
                SET equipment_mac = observed_mac,
                    dhcp_status = 'ok',
                    last_status_change = datetime('now'),
                    last_checked = datetime('now')
                WHERE port_id = ?
                """,
                (port["port_id"],),
            )
            # ...and refresh the lease for the new MAC (simulated provisioning).
            cursor.execute(
                """
                UPDATE ip_assignments
                SET mac_address = ?, status = 'active', last_seen = datetime('now')
                WHERE customer_id = ?
                """,
                (observed, customer_id),
            )

        logger.info(f"[SIM] MAC bound for {customer_id}: {old_mac} -> {observed}")
        return {
            "success": True,
            "customer_id": customer_id,
            "old_mac": old_mac,
            "new_mac": observed,
            "message": (
                f"MAC pririštas (simuliuota): {observed}. Autorizacija atnaujinta, "
                "DHCP aktyvus. Paprašykite kliento patikrinti ryšį už ~1 minutės."
            ),
        }

    except Exception as e:
        logger.error(f"Error in bind_port_mac: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def reset_customer_port(db: DatabaseConnection, customer_id: str) -> dict[str, Any]:
    """
    SIMULATED: bounce the customer's switch port / session.

    Used after a MAC bind (forces re-auth) and for the B3 "port freeze" case.
    """
    logger.info(f"[SIM] Resetting port for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT port_id, status FROM ports WHERE customer_id = ?",
                (customer_id,),
            )
            port = cursor.fetchone()

        if not port:
            return {
                "success": False,
                "error": "no_port_found",
                "message": "Klientui nerastas tinklo portas.",
            }

        port = dict(port)

        with db.transaction() as cursor:
            cursor.execute(
                """
                UPDATE ports
                SET last_status_change = datetime('now'), last_checked = datetime('now')
                WHERE port_id = ?
                """,
                (port["port_id"],),
            )

        logger.info(f"[SIM] Port {port['port_id']} reset for {customer_id}")
        return {
            "success": True,
            "customer_id": customer_id,
            "port_id": port["port_id"],
            "message": (
                "Portas perkrautas (simuliuota). Sesija atnaujinta — paprašykite "
                "kliento palaukti ~1 minutę ir patikrinti ryšį."
            ),
        }

    except Exception as e:
        logger.error(f"Error in reset_customer_port: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}
