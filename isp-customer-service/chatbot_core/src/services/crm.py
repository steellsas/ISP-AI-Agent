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


def get_customer_by_address(city: str, street: str, house_number: str, apartment_number: str = None) -> dict:
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
    return lookup_customer_by_address(db, {
        "city": city,
        "street": street,
        "house_number": house_number,
        "apartment_number": apartment_number
    })