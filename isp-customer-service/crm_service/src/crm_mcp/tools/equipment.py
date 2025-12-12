"""
Equipment Management Tools
Query customer equipment (routers, decoders, etc.)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def get_customer_equipment(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Get all equipment for a customer.

    Args:
        db: Database connection
        customer_id: Customer ID

    Returns:
        Equipment list with details
    """
    logger.info(f"Getting equipment for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    equipment_id,
                    equipment_type,
                    model,
                    serial_number,
                    mac_address,
                    installed_date,
                    status,
                    notes
                FROM customer_equipment
                WHERE customer_id = ?
                ORDER BY 
                    CASE equipment_type
                        WHEN 'router' THEN 1
                        WHEN 'modem' THEN 2
                        WHEN 'ont' THEN 3
                        WHEN 'decoder' THEN 4
                        ELSE 5
                    END,
                    installed_date DESC
            """,
                (customer_id,),
            )

            equipment_list = [dict(row) for row in cursor.fetchall()]

        if not equipment_list:
            return {
                "success": True,
                "equipment": [],
                "message": "Klientas neturi užregistruotos įrangos",
            }

        # Group by type
        equipment_by_type = {}
        for item in equipment_list:
            eq_type = item["equipment_type"]
            if eq_type not in equipment_by_type:
                equipment_by_type[eq_type] = []
            equipment_by_type[eq_type].append(item)

        # Summary
        summary = {
            "total_equipment": len(equipment_list),
            "by_type": {eq_type: len(items) for eq_type, items in equipment_by_type.items()},
        }

        logger.info(f"Found {len(equipment_list)} equipment items for {customer_id}")

        return {
            "success": True,
            "equipment": equipment_list,
            "equipment_by_type": equipment_by_type,
            "summary": summary,
        }

    except Exception as e:
        logger.error(f"Error in get_customer_equipment: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def get_equipment_by_type(
    db: DatabaseConnection, customer_id: str, equipment_type: str
) -> Dict[str, Any]:
    """
    Get specific type of equipment for customer.

    Args:
        db: Database connection
        customer_id: Customer ID
        equipment_type: Type (router, modem, decoder, etc.)

    Returns:
        Equipment list of specified type
    """
    logger.info(f"Getting {equipment_type} equipment for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM customer_equipment
                WHERE customer_id = ? 
                    AND equipment_type = ?
                    AND status = 'active'
                ORDER BY installed_date DESC
            """,
                (customer_id, equipment_type),
            )

            equipment_list = [dict(row) for row in cursor.fetchall()]

        return {
            "success": True,
            "equipment_type": equipment_type,
            "equipment": equipment_list,
            "count": len(equipment_list),
        }

    except Exception as e:
        logger.error(f"Error in get_equipment_by_type: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def get_equipment_by_mac(db: DatabaseConnection, mac_address: str) -> Dict[str, Any]:
    """
    Find equipment by MAC address.

    Args:
        db: Database connection
        mac_address: MAC address

    Returns:
        Equipment details
    """
    logger.info(f"Looking up equipment by MAC: {mac_address}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    ce.*,
                    c.first_name,
                    c.last_name,
                    c.phone
                FROM customer_equipment ce
                JOIN customers c ON ce.customer_id = c.customer_id
                WHERE ce.mac_address = ?
            """,
                (mac_address,),
            )

            result = cursor.fetchone()

        if not result:
            return {
                "success": False,
                "error": "not_found",
                "message": f"Įranga su MAC adresu {mac_address} nerasta",
            }

        equipment_data = dict(result)

        return {"success": True, "equipment": equipment_data}

    except Exception as e:
        logger.error(f"Error in get_equipment_by_mac: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}
