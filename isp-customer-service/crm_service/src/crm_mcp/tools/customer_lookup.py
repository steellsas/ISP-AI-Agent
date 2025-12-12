"""
Customer Lookup Tools
Find customers by address with fuzzy matching support
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from Levenshtein import ratio
from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def normalize_street_name(street: str) -> str:
    """
    Normalize street name for matching.

    Removes common suffixes like 'g.', 'gatvė', etc.

    Args:
        street: Street name

    Returns:
        Normalized street name
    """
    # Remove common Lithuanian street suffixes
    suffixes = ["g.", "g", "gatvė", "gatve"]
    street_lower = street.lower().strip()

    for suffix in suffixes:
        if street_lower.endswith(suffix):
            street_lower = street_lower[: -len(suffix)].strip()

    return street_lower


def fuzzy_match_street(
    input_street: str, db_streets: List[str], threshold: float = 0.7
) -> Optional[str]:
    """
    Find best matching street using fuzzy matching.

    Args:
        input_street: User input street name
        db_streets: List of streets from database
        threshold: Minimum similarity ratio (0-1)

    Returns:
        Best matching street or None
    """
    input_normalized = normalize_street_name(input_street)

    best_match = None
    best_ratio = 0.0

    for db_street in db_streets:
        db_normalized = normalize_street_name(db_street)
        similarity = ratio(input_normalized, db_normalized)

        if similarity > best_ratio:
            best_ratio = similarity
            best_match = db_street

    if best_ratio >= threshold:
        logger.info(f"Fuzzy match: '{input_street}' -> '{best_match}' (ratio: {best_ratio:.2f})")
        return best_match

    return None


def lookup_customer_by_address(db: DatabaseConnection, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lookup customer by address with fuzzy matching.

    Args:
        db: Database connection
        args: Address parameters (city, street, house_number, apartment_number)

    Returns:
        Customer data or error
    """
    city = args.get("city", "").strip()
    street = args.get("street", "").strip()
    house_number = args.get("house_number", "").strip()
    apartment_number = (
        args.get("apartment_number", "").strip() if args.get("apartment_number") else None
    )

    logger.info(
        f"Looking up customer: {city}, {street} {house_number}"
        + (f"-{apartment_number}" if apartment_number else "")
    )

    try:
        # Step 1: Get all streets in the city for fuzzy matching
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT street 
                FROM addresses 
                WHERE LOWER(city) = LOWER(?)
            """,
                (city,),
            )

            db_streets = [row["street"] for row in cursor.fetchall()]

        if not db_streets:
            return {
                "success": False,
                "error": "city_not_found",
                "message": f"Miestas '{city}' nerastas sistemoje",
            }

        # Step 2: Find best matching street
        matched_street = fuzzy_match_street(street, db_streets)

        if not matched_street:
            return {
                "success": False,
                "error": "street_not_found",
                "message": f"Gatvė '{street}' nerasta mieste {city}",
                "available_streets": db_streets[:10],  # Show first 10 streets
            }

        # Step 3: Find customer by exact address
        query = """
            SELECT 
                c.customer_id,
                c.first_name,
                c.last_name,
                c.phone,
                c.email,
                c.status,
                a.address_id,
                a.city,
                a.street,
                a.house_number,
                a.apartment_number,
                a.full_address
            FROM customers c
            JOIN addresses a ON c.customer_id = a.customer_id
            WHERE LOWER(a.city) = LOWER(?)
                AND LOWER(a.street) = LOWER(?)
                AND a.house_number = ?
        """

        params = [city, matched_street, house_number]

        if apartment_number:
            query += " AND a.apartment_number = ?"
            params.append(apartment_number)
        else:
            query += " AND (a.apartment_number IS NULL OR a.apartment_number = '')"

        with db.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()

        if not result:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Klientas nerasta adresu: {city}, {matched_street} {house_number}"
                + (f"-{apartment_number}" if apartment_number else ""),
                "matched_street": matched_street,
            }

        # Found customer
        customer_data = dict(result)

        logger.info(
            f"Found customer: {customer_data['customer_id']} - {customer_data['first_name']} {customer_data['last_name']}"
        )

        return {
            "success": True,
            "customer": {
                "customer_id": customer_data["customer_id"],
                "first_name": customer_data["first_name"],
                "last_name": customer_data["last_name"],
                "phone": customer_data["phone"],
                "email": customer_data["email"],
                "status": customer_data["status"],
                "address": {
                    "city": customer_data["city"],
                    "street": customer_data["street"],
                    "house_number": customer_data["house_number"],
                    "apartment_number": customer_data["apartment_number"],
                    "full_address": customer_data["full_address"],
                },
            },
        }

    except Exception as e:
        logger.error(f"Error in lookup_customer_by_address: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def lookup_customer_by_phone(db: DatabaseConnection, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lookup customer by phone number using repository pattern.

    Args:
        db: Database connection
        args: Phone number parameter

    Returns:
        Customer data or error
    """
    from repository.customer_repo import CustomerRepository

    phone = args.get("phone_number", "").strip()

    logger.info(f"tools :Looking up customer by phone: {phone}")

    if not phone:
        return {
            "success": False,
            "error": "missing_phone",
            "message": "Telefono numeris nebuvo pateiktas",
            "found": False,
        }

    try:
        # Initialize repository
        repo = CustomerRepository(db)

        # Find customer by phone
        customer = repo.find_by_phone(phone)

        if not customer:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Klientas su telefonu {phone} nerastas",
                "found": False,
            }

        # Get customer details using repository methods
        customer_id = customer.customer_id
        addresses = repo.get_addresses(customer_id)
        services = repo.get_service_plans(customer_id, active_only=True)
        equipment = repo.get_equipment(customer_id, active_only=True)

        logger.info(f"Found customer: {customer_id} - {customer.first_name} {customer.last_name}")

        # Convert to dicts
        return {
            "success": True,
            "found": True,
            "customer": {
                "customer_id": customer.customer_id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "phone": customer.phone,
                "email": customer.email,
                "status": customer.status,
            },
            "addresses": [
                {
                    "address_id": addr.address_id,
                    "city": addr.city,
                    "street": addr.street,
                    "house_number": addr.house_number,
                    "apartment_number": addr.apartment_number,
                    "full_address": addr.full_address,
                    "is_primary": addr.is_primary,
                }
                for addr in addresses
            ],
            "services": [
                {
                    "service_plan_id": svc.plan_id,
                    "plan_name": svc.plan_name,
                    "plan_type": svc.service_type,
                    "speed_mbps": svc.speed_mbps,
                    "monthly_fee": float(svc.price) if svc.price else None,
                    "status": svc.status,
                }
                for svc in services
            ],
            "equipment": [
                {
                    "equipment_id": eq.equipment_id,
                    "equipment_type": eq.equipment_type,
                    "model": eq.model,
                    "serial_number": eq.serial_number,
                    "status": eq.status,
                }
                for eq in equipment
            ],
        }

    except Exception as e:
        logger.error(f"Error in lookup_customer_by_phone: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida ieškant kliento: {str(e)}",
        }


def get_customer_details(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Get comprehensive customer information.

    Args:
        db: Database connection
        customer_id: Customer ID

    Returns:
        Complete customer data including services, equipment, history
    """
    logger.info(f"Getting details for customer: {customer_id}")

    try:
        # Customer basic info
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM customers WHERE customer_id = ?
            """,
                (customer_id,),
            )
            customer = cursor.fetchone()

        if not customer:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Klientas {customer_id} nerastas",
            }

        customer_dict = dict(customer)

        # Get addresses
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM addresses WHERE customer_id = ?
            """,
                (customer_id,),
            )
            addresses = [dict(row) for row in cursor.fetchall()]

        # Get service plans
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM service_plans 
                WHERE customer_id = ? AND status = 'active'
            """,
                (customer_id,),
            )
            services = [dict(row) for row in cursor.fetchall()]

        # Get equipment
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM customer_equipment 
                WHERE customer_id = ? AND status = 'active'
            """,
                (customer_id,),
            )
            equipment = [dict(row) for row in cursor.fetchall()]

        # Get recent tickets
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM tickets 
                WHERE customer_id = ?
                ORDER BY created_at DESC
                LIMIT 5
            """,
                (customer_id,),
            )
            tickets = [dict(row) for row in cursor.fetchall()]

        return {
            "success": True,
            "customer": customer_dict,
            "addresses": addresses,
            "services": services,
            "equipment": equipment,
            "recent_tickets": tickets,
        }

    except Exception as e:
        logger.error(f"Error in get_customer_details: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}
