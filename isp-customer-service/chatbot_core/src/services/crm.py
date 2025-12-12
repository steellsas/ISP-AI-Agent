"""
CRM Service - Direct integration with crm_service tools
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent.parent.parent
crm_service_path = project_root / "crm_service" / "src"
shared_path = project_root / "shared" / "src"

for p in [str(crm_service_path), str(shared_path)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from database import init_database
from crm_mcp.tools.customer_lookup import lookup_customer_by_phone, lookup_customer_by_address
from crm_mcp.tools.tickets import create_ticket
from utils import get_logger

logger = get_logger(__name__)

# Database path
DB_PATH = project_root / "database" / "isp_database.db"

# Cached DB connection
_db = None


def get_db():
    """Get or create database connection."""
    global _db
    if _db is None:
        logger.info(f"Initializing database: {DB_PATH}")
        _db = init_database(DB_PATH)
    return _db


def get_customer_by_phone(phone_number: str) -> dict:
    """
    Lookup customer by phone number.

    Args:
        phone_number: Phone number

    Returns:
        Result dict with customer data or error
    """
    logger.info(f"CRM lookup by phone: {phone_number}")
    db = get_db()
    return lookup_customer_by_phone(db, {"phone_number": phone_number})


def get_customer_by_address(
    city: str, street: str, house_number: str, apartment_number: str = None
) -> dict:
    """
    Lookup customer by address.

    Args:
        city: City name
        street: Street name
        house_number: House number
        apartment_number: Apartment (optional)

    Returns:
        Result dict with customer data or error
    """
    logger.info(f"CRM lookup by address: {city}, {street} {house_number}")
    db = get_db()
    return lookup_customer_by_address(
        db,
        {
            "city": city,
            "street": street,
            "house_number": house_number,
            "apartment_number": apartment_number,
        },
    )


def create_support_ticket(
    customer_id: str,
    ticket_type: str,
    summary: str,
    details: str = None,
    priority: str = "medium",
    troubleshooting_steps: list = None,
) -> dict:
    """
    Create support ticket in CRM.

    Args:
        customer_id: Customer ID
        ticket_type: Type (resolved, technician_visit, network_issue, etc.)
        summary: Brief summary
        details: Detailed description
        priority: low/medium/high/critical
        troubleshooting_steps: List of completed troubleshooting steps

    Returns:
        Result dict with ticket_id or error
    """
    logger.info(f"Creating ticket for customer: {customer_id}, type: {ticket_type}")
    db = get_db()

    # Import tool
    try:
        # Add crm_service tools path
        # project_root = Path(__file__).parent.parent.parent.parent
        # crm_tools_path = project_root / "crm_service" / "src" / "tools"
        # if str(crm_tools_path.parent) not in sys.path:
        #     sys.path.insert(0, str(crm_tools_path.parent))

        # from tools.tickets import create_ticket

        # Build details with troubleshooting steps
        full_details = details or ""
        if troubleshooting_steps:
            steps_text = "\n".join(
                [f"- Žingsnis {i+1}: {step}" for i, step in enumerate(troubleshooting_steps)]
            )
            full_details += f"\n\nAtlikti troubleshooting žingsniai:\n{steps_text}"

        result = create_ticket(
            db,
            {
                "customer_id": customer_id,
                "ticket_type": ticket_type,
                "summary": summary,
                "details": full_details,
                "priority": priority,
                "troubleshooting_steps": (
                    str(troubleshooting_steps) if troubleshooting_steps else None
                ),
            },
        )

        return result

    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return {
            "success": False,
            "error": "ticket_creation_failed",
            "message": f"Nepavyko sukurti užklausos: {str(e)}",
        }
