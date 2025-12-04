"""
Network Repository
Clean data access layer for network-related queries
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from isp_types import Switch, Port, IPAssignment, AreaOutage, BandwidthLog, PortStatus
from utils import get_logger

logger = get_logger(__name__)


class NetworkRepository:
    """Repository for network data operations."""

    def __init__(self, db: DatabaseConnection):
        """
        Initialize repository.

        Args:
            db: Database connection
        """
        self.db = db

    # ========== Switch Methods ==========

    def find_switch_by_id(self, switch_id: str) -> Optional[Switch]:
        """
        Find switch by ID.

        Args:
            switch_id: Switch ID

        Returns:
            Switch object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM switches WHERE switch_id = ?
                """,
                    (switch_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Switch(**dict(result))

        except Exception as e:
            logger.error(f"Error finding switch {switch_id}: {e}")
            return None

    def find_switch_by_customer(self, customer_id: str) -> Optional[Switch]:
        """
        Find switch serving a customer.

        Args:
            customer_id: Customer ID

        Returns:
            Switch object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT s.*
                    FROM switches s
                    JOIN ports p ON s.switch_id = p.switch_id
                    WHERE p.customer_id = ?
                    LIMIT 1
                """,
                    (customer_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Switch(**dict(result))

        except Exception as e:
            logger.error(f"Error finding switch for customer {customer_id}: {e}")
            return None

    def get_all_switches(self, status: Optional[str] = None) -> List[Switch]:
        """
        Get all switches.

        Args:
            status: Filter by status (optional)

        Returns:
            List of Switch objects
        """
        try:
            query = "SELECT * FROM switches"
            params = []

            if status:
                query += " WHERE status = ?"
                params.append(status)

            query += " ORDER BY switch_name"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [Switch(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting switches: {e}")
            return []

    def get_switch_statistics(self, switch_id: str) -> Dict[str, Any]:
        """
        Get port statistics for a switch.

        Args:
            switch_id: Switch ID

        Returns:
            Statistics dictionary
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        COUNT(*) as total_ports,
                        SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) as active_ports,
                        SUM(CASE WHEN status = 'down' THEN 1 ELSE 0 END) as down_ports,
                        SUM(CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END) as assigned_ports
                    FROM ports
                    WHERE switch_id = ?
                """,
                    (switch_id,),
                )

                result = cursor.fetchone()

            return dict(result)

        except Exception as e:
            logger.error(f"Error getting switch statistics: {e}")
            return {}

    # ========== Port Methods ==========

    def find_port_by_id(self, port_id: str) -> Optional[Port]:
        """
        Find port by ID.

        Args:
            port_id: Port ID

        Returns:
            Port object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ports WHERE port_id = ?
                """,
                    (port_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Port(**dict(result))

        except Exception as e:
            logger.error(f"Error finding port {port_id}: {e}")
            return None

    def find_ports_by_customer(self, customer_id: str) -> List[Port]:
        """
        Find all ports for a customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of Port objects
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ports 
                    WHERE customer_id = ?
                    ORDER BY switch_id, port_number
                """,
                    (customer_id,),
                )

                results = cursor.fetchall()

            return [Port(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding ports for customer {customer_id}: {e}")
            return []

    def find_ports_by_mac(self, mac_address: str) -> List[Port]:
        """
        Find ports by equipment MAC address.

        Args:
            mac_address: MAC address

        Returns:
            List of Port objects
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ports 
                    WHERE equipment_mac = ?
                """,
                    (mac_address,),
                )

                results = cursor.fetchall()

            return [Port(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding ports by MAC {mac_address}: {e}")
            return []

    def get_ports_by_switch(self, switch_id: str, status: Optional[str] = None) -> List[Port]:
        """
        Get all ports on a switch.

        Args:
            switch_id: Switch ID
            status: Filter by status (optional)

        Returns:
            List of Port objects
        """
        try:
            query = "SELECT * FROM ports WHERE switch_id = ?"
            params = [switch_id]

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY port_number"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [Port(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting ports for switch {switch_id}: {e}")
            return []

    def count_ports_by_status(self, switch_id: Optional[str] = None) -> Dict[str, int]:
        """
        Count ports by status.

        Args:
            switch_id: Filter by switch (optional)

        Returns:
            Dictionary of status counts
        """
        try:
            query = "SELECT status, COUNT(*) as count FROM ports"
            params = []

            if switch_id:
                query += " WHERE switch_id = ?"
                params.append(switch_id)

            query += " GROUP BY status"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return {row["status"]: row["count"] for row in results}

        except Exception as e:
            logger.error(f"Error counting ports: {e}")
            return {}

    # ========== IP Assignment Methods ==========

    def find_ip_by_customer(self, customer_id: str, active_only: bool = True) -> List[IPAssignment]:
        """
        Find IP assignments for customer.

        Args:
            customer_id: Customer ID
            active_only: Only return active assignments

        Returns:
            List of IPAssignment objects
        """
        try:
            query = "SELECT * FROM ip_assignments WHERE customer_id = ?"
            params = [customer_id]

            if active_only:
                query += " AND status = 'active'"

            query += " ORDER BY assigned_at DESC"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [IPAssignment(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding IP for customer {customer_id}: {e}")
            return []

    def find_ip_by_address(self, ip_address: str) -> Optional[IPAssignment]:
        """
        Find IP assignment by address.

        Args:
            ip_address: IP address

        Returns:
            IPAssignment object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ip_assignments 
                    WHERE ip_address = ?
                    ORDER BY assigned_at DESC
                    LIMIT 1
                """,
                    (ip_address,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return IPAssignment(**dict(result))

        except Exception as e:
            logger.error(f"Error finding IP {ip_address}: {e}")
            return None

    def find_ip_by_mac(self, mac_address: str) -> List[IPAssignment]:
        """
        Find IP assignments by MAC address.

        Args:
            mac_address: MAC address

        Returns:
            List of IPAssignment objects
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM ip_assignments 
                    WHERE mac_address = ?
                    ORDER BY assigned_at DESC
                """,
                    (mac_address,),
                )

                results = cursor.fetchall()

            return [IPAssignment(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding IP by MAC {mac_address}: {e}")
            return []

    # ========== Bandwidth Log Methods ==========

    def get_bandwidth_logs(
        self, customer_id: str, limit: int = 10, measurement_type: Optional[str] = None
    ) -> List[BandwidthLog]:
        """
        Get bandwidth measurement logs.

        Args:
            customer_id: Customer ID
            limit: Maximum number of logs
            measurement_type: Filter by type (optional)

        Returns:
            List of BandwidthLog objects
        """
        try:
            query = "SELECT * FROM bandwidth_logs WHERE customer_id = ?"
            params = [customer_id]

            if measurement_type:
                query += " AND measurement_type = ?"
                params.append(measurement_type)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [BandwidthLog(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting bandwidth logs: {e}")
            return []

    def get_bandwidth_statistics(self, customer_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get bandwidth statistics for a period.

        Args:
            customer_id: Customer ID
            days: Number of days to analyze

        Returns:
            Statistics dictionary
        """
        try:
            date_threshold = (datetime.now() - timedelta(days=days)).isoformat()

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 
                        AVG(download_mbps) as avg_download,
                        MAX(download_mbps) as max_download,
                        MIN(download_mbps) as min_download,
                        AVG(upload_mbps) as avg_upload,
                        MAX(upload_mbps) as max_upload,
                        MIN(upload_mbps) as min_upload,
                        AVG(latency_ms) as avg_latency,
                        MAX(latency_ms) as max_latency,
                        MIN(latency_ms) as min_latency,
                        COUNT(*) as measurement_count
                    FROM bandwidth_logs
                    WHERE customer_id = ? AND timestamp >= ?
                """,
                    (customer_id, date_threshold),
                )

                result = cursor.fetchone()

            return dict(result) if result else {}

        except Exception as e:
            logger.error(f"Error getting bandwidth statistics: {e}")
            return {}

    # ========== Area Outage Methods ==========

    def find_active_outages(self, city: str, street: Optional[str] = None) -> List[AreaOutage]:
        """
        Find active outages in an area.

        Args:
            city: City name
            street: Street name (optional)

        Returns:
            List of AreaOutage objects
        """
        try:
            query = """
                SELECT * FROM area_outages 
                WHERE LOWER(city) = LOWER(?)
                    AND status IN ('active', 'investigating')
            """
            params = [city]

            if street:
                query += " AND (street IS NULL OR LOWER(street) = LOWER(?))"
                params.append(street)

            query += " ORDER BY severity DESC, reported_at DESC"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [AreaOutage(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding outages in {city}: {e}")
            return []

    def find_outage_by_id(self, outage_id: str) -> Optional[AreaOutage]:
        """
        Find outage by ID.

        Args:
            outage_id: Outage ID

        Returns:
            AreaOutage object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM area_outages WHERE outage_id = ?
                """,
                    (outage_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return AreaOutage(**dict(result))

        except Exception as e:
            logger.error(f"Error finding outage {outage_id}: {e}")
            return None

    def get_outage_history(self, city: str, days: int = 30) -> List[AreaOutage]:
        """
        Get outage history for an area.

        Args:
            city: City name
            days: Number of days to look back

        Returns:
            List of AreaOutage objects
        """
        try:
            date_threshold = (datetime.now() - timedelta(days=days)).isoformat()

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM area_outages
                    WHERE LOWER(city) = LOWER(?)
                        AND reported_at >= ?
                    ORDER BY reported_at DESC
                """,
                    (city, date_threshold),
                )

                results = cursor.fetchall()

            return [AreaOutage(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error getting outage history for {city}: {e}")
            return []

    def count_active_outages(self, city: Optional[str] = None) -> int:
        """
        Count active outages.

        Args:
            city: Filter by city (optional)

        Returns:
            Number of active outages
        """
        try:
            query = """
                SELECT COUNT(*) as count 
                FROM area_outages 
                WHERE status IN ('active', 'investigating')
            """
            params = []

            if city:
                query += " AND LOWER(city) = LOWER(?)"
                params.append(city)

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()

            return dict(result)["count"]

        except Exception as e:
            logger.error(f"Error counting active outages: {e}")
            return 0

    # ========== Diagnostic Helper Methods ==========

    def get_customer_network_summary(self, customer_id: str) -> Dict[str, Any]:
        """
        Get comprehensive network summary for customer.

        Args:
            customer_id: Customer ID

        Returns:
            Dictionary with all network data
        """
        try:
            return {
                "ports": [p.model_dump() for p in self.find_ports_by_customer(customer_id)],
                "ip_assignments": [ip.model_dump() for ip in self.find_ip_by_customer(customer_id)],
                "recent_bandwidth": [
                    log.model_dump() for log in self.get_bandwidth_logs(customer_id, limit=5)
                ],
                "switch": (
                    self.find_switch_by_customer(customer_id).model_dump()
                    if self.find_switch_by_customer(customer_id)
                    else None
                ),
            }
        except Exception as e:
            logger.error(f"Error getting network summary for {customer_id}: {e}")
            return {}
