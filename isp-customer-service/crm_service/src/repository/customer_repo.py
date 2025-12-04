"""
Customer Repository
Clean data access layer for customer-related queries
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from isp_types import Customer, Address, ServicePlan, CustomerEquipment
from utils import get_logger

logger = get_logger(__name__)


class CustomerRepository:
    """Repository for customer data operations."""

    def __init__(self, db: DatabaseConnection):
        """
        Initialize repository.

        Args:
            db: Database connection
        """
        self.db = db

    def find_by_id(self, customer_id: str) -> Optional[Customer]:
        """
        Find customer by ID.

        Args:
            customer_id: Customer ID

        Returns:
            Customer object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM customers WHERE customer_id = ?
                """,
                    (customer_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Customer(**dict(result))

        except Exception as e:
            logger.error(f"Error finding customer {customer_id}: {e}")
            return None

    def find_by_address(
        self, city: str, street: str, house_number: str, apartment_number: Optional[str] = None
    ) -> Optional[Customer]:
        """
        Find customer by address.

        Args:
            city: City name
            street: Street name
            house_number: House number
            apartment_number: Apartment number (optional)

        Returns:
            Customer object or None
        """
        try:
            query = """
                SELECT c.*
                FROM customers c
                JOIN addresses a ON c.customer_id = a.customer_id
                WHERE LOWER(a.city) = LOWER(?)
                    AND LOWER(a.street) = LOWER(?)
                    AND a.house_number = ?
            """

            params = [city, street, house_number]

            if apartment_number:
                query += " AND a.apartment_number = ?"
                params.append(apartment_number)
            else:
                query += " AND (a.apartment_number IS NULL OR a.apartment_number = '')"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()

            if not result:
                return None

            return Customer(**dict(result))

        except Exception as e:
            logger.error(f"Error finding customer by address: {e}")
            return None

    def find_by_phone(self, phone: str) -> Optional[Customer]:
        """
        Find customer by phone number.

        Args:
            phone: Phone number

        Returns:
            Customer object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM customers WHERE phone = ?
                """,
                    (phone,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Customer(**dict(result))

        except Exception as e:
            logger.error(f"Error finding customer by phone {phone}: {e}")
            return None

    def find_by_email(self, email: str) -> Optional[Customer]:
        """
        Find customer by email.

        Args:
            email: Email address

        Returns:
            Customer object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM customers WHERE email = ?
                """,
                    (email,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Customer(**dict(result))

        except Exception as e:
            logger.error(f"Error finding customer by email {email}: {e}")
            return None

    def get_addresses(self, customer_id: str) -> List[Address]:
        """
        Get all addresses for customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of Address objects
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM addresses WHERE customer_id = ?
                    ORDER BY is_primary DESC
                """,
                    (customer_id,),
                )

                results = cursor.fetchall()

            return [Address(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting addresses for {customer_id}: {e}")
            return []

    def get_primary_address(self, customer_id: str) -> Optional[Address]:
        """
        Get primary address for customer.

        Args:
            customer_id: Customer ID

        Returns:
            Address object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM addresses 
                    WHERE customer_id = ? AND is_primary = 1
                """,
                    (customer_id,),
                )

                result = cursor.fetchone()

            if not result:
                # If no primary, get first address
                with self.db.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT * FROM addresses 
                        WHERE customer_id = ?
                        LIMIT 1
                    """,
                        (customer_id,),
                    )
                    result = cursor.fetchone()

            if not result:
                return None

            return Address(**dict(result))

        except Exception as e:
            logger.error(f"Error getting primary address for {customer_id}: {e}")
            return None

    def get_service_plans(self, customer_id: str, active_only: bool = True) -> List[ServicePlan]:
        """
        Get service plans for customer.

        Args:
            customer_id: Customer ID
            active_only: Only return active plans

        Returns:
            List of ServicePlan objects
        """
        try:
            query = "SELECT * FROM service_plans WHERE customer_id = ?"
            params = [customer_id]

            if active_only:
                query += " AND status = 'active'"

            query += " ORDER BY activation_date DESC"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [ServicePlan(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting service plans for {customer_id}: {e}")
            return []

    def get_equipment(self, customer_id: str, active_only: bool = True) -> List[CustomerEquipment]:
        """
        Get equipment for customer.

        Args:
            customer_id: Customer ID
            active_only: Only return active equipment

        Returns:
            List of CustomerEquipment objects
        """
        try:
            query = "SELECT * FROM customer_equipment WHERE customer_id = ?"
            params = [customer_id]

            if active_only:
                query += " AND status = 'active'"

            query += " ORDER BY installed_date DESC"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [CustomerEquipment(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting equipment for {customer_id}: {e}")
            return []

    def get_customer_summary(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive customer summary.

        Args:
            customer_id: Customer ID

        Returns:
            Dictionary with all customer data
        """
        customer = self.find_by_id(customer_id)
        if not customer:
            return None

        return {
            "customer": customer.model_dump(),
            "addresses": [addr.model_dump() for addr in self.get_addresses(customer_id)],
            "services": [svc.model_dump() for svc in self.get_service_plans(customer_id)],
            "equipment": [eq.model_dump() for eq in self.get_equipment(customer_id)],
        }

    def get_streets_in_city(self, city: str) -> List[str]:
        """
        Get all unique streets in a city.

        Args:
            city: City name

        Returns:
            List of street names
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT street 
                    FROM addresses 
                    WHERE LOWER(city) = LOWER(?)
                    ORDER BY street
                """,
                    (city,),
                )

                results = cursor.fetchall()

            return [row["street"] for row in results]

        except Exception as e:
            logger.error(f"Error getting streets in {city}: {e}")
            return []

    def get_cities(self) -> List[str]:
        """
        Get all unique cities.

        Returns:
            List of city names
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT city 
                    FROM addresses 
                    ORDER BY city
                """
                )

                results = cursor.fetchall()

            return [row["city"] for row in results]

        except Exception as e:
            logger.error(f"Error getting cities: {e}")
            return []

    def count_customers(self, status: Optional[str] = None) -> int:
        """
        Count customers.

        Args:
            status: Filter by status (optional)

        Returns:
            Customer count
        """
        try:
            query = "SELECT COUNT(*) as count FROM customers"
            params = []

            if status:
                query += " WHERE status = ?"
                params.append(status)

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()

            return dict(result)["count"]

        except Exception as e:
            logger.error(f"Error counting customers: {e}")
            return 0

    def search_customers(self, query: str, limit: int = 10) -> List[Customer]:
        """
        Search customers by name, phone, or email.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching customers
        """
        try:
            search_pattern = f"%{query}%"

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM customers
                    WHERE first_name LIKE ?
                        OR last_name LIKE ?
                        OR phone LIKE ?
                        OR email LIKE ?
                    LIMIT ?
                """,
                    (search_pattern, search_pattern, search_pattern, search_pattern, limit),
                )

                results = cursor.fetchall()

            return [Customer(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error searching customers: {e}")
            return []
