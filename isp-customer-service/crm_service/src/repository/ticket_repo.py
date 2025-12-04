"""
Ticket Repository
Clean data access layer for ticket-related queries
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from isp_types import Ticket, TicketType, TicketPriority, TicketStatus
from utils import get_logger

logger = get_logger(__name__)


class TicketRepository:
    """Repository for ticket data operations."""

    def __init__(self, db: DatabaseConnection):
        """
        Initialize repository.

        Args:
            db: Database connection
        """
        self.db = db

    def generate_ticket_id(self) -> str:
        """Generate unique ticket ID."""
        return f"TKT{uuid.uuid4().hex[:8].upper()}"

    def create(
        self,
        customer_id: str,
        ticket_type: str,
        summary: str,
        priority: str = "medium",
        details: Optional[str] = None,
        troubleshooting_steps: Optional[str] = None,
    ) -> Optional[Ticket]:
        """
        Create a new ticket.

        Args:
            customer_id: Customer ID
            ticket_type: Type of ticket
            summary: Brief summary
            priority: Priority level
            details: Detailed description
            troubleshooting_steps: Steps already taken

        Returns:
            Created Ticket object or None
        """
        try:
            ticket_id = self.generate_ticket_id()
            now = datetime.now().isoformat()

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tickets (
                        ticket_id,
                        customer_id,
                        ticket_type,
                        priority,
                        status,
                        summary,
                        details,
                        troubleshooting_steps,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        ticket_id,
                        customer_id,
                        ticket_type,
                        priority,
                        "open",
                        summary,
                        details,
                        troubleshooting_steps,
                        now,
                        now,
                    ),
                )

            logger.info(f"Created ticket {ticket_id} for customer {customer_id}")

            # Add to history
            self._add_history(
                customer_id, "ticket_created", f"Ticket created: {summary}", ticket_id
            )

            return self.find_by_id(ticket_id)

        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            return None

    def find_by_id(self, ticket_id: str) -> Optional[Ticket]:
        """
        Find ticket by ID.

        Args:
            ticket_id: Ticket ID

        Returns:
            Ticket object or None
        """
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM tickets WHERE ticket_id = ?
                """,
                    (ticket_id,),
                )

                result = cursor.fetchone()

            if not result:
                return None

            return Ticket(**dict(result))

        except Exception as e:
            logger.error(f"Error finding ticket {ticket_id}: {e}")
            return None

    def find_by_customer(
        self, customer_id: str, status: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Ticket]:
        """
        Find tickets for a customer.

        Args:
            customer_id: Customer ID
            status: Filter by status (optional)
            limit: Maximum results (optional)

        Returns:
            List of Ticket objects
        """
        try:
            query = "SELECT * FROM tickets WHERE customer_id = ?"
            params = [customer_id]

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            return [Ticket(**dict(row)) for row in results]

        except Exception as e:
            logger.error(f"Error finding tickets for customer {customer_id}: {e}")
            return []

    def get_open_tickets(self, customer_id: str) -> List[Ticket]:
        """
        Get all open tickets for customer.

        Args:
            customer_id: Customer ID

        Returns:
            List of open Ticket objects
        """
        return self.find_by_customer(customer_id, status="open")

    def get_recent_tickets(self, customer_id: str, limit: int = 5) -> List[Ticket]:
        """
        Get recent tickets for customer.

        Args:
            customer_id: Customer ID
            limit: Maximum results

        Returns:
            List of recent Ticket objects
        """
        return self.find_by_customer(customer_id, limit=limit)

    def update_status(
        self, ticket_id: str, status: str, resolution_summary: Optional[str] = None
    ) -> bool:
        """
        Update ticket status.

        Args:
            ticket_id: Ticket ID
            status: New status
            resolution_summary: Resolution summary (for closed tickets)

        Returns:
            True if successful
        """
        try:
            update_query = """
                UPDATE tickets 
                SET status = ?, updated_at = ?
            """
            params = [status, datetime.now().isoformat()]

            if status == "closed":
                update_query += ", resolved_at = ?"
                params.append(datetime.now().isoformat())

                if resolution_summary:
                    update_query += ", resolution_summary = ?"
                    params.append(resolution_summary)

            update_query += " WHERE ticket_id = ?"
            params.append(ticket_id)

            with self.db.cursor() as cursor:
                cursor.execute(update_query, params)

            # Get customer_id for history
            ticket = self.find_by_id(ticket_id)
            if ticket and status == "closed":
                self._add_history(
                    ticket.customer_id,
                    "ticket_resolved",
                    f"Ticket resolved: {resolution_summary or 'No details'}",
                    ticket_id,
                )

            logger.info(f"Updated ticket {ticket_id} status to {status}")
            return True

        except Exception as e:
            logger.error(f"Error updating ticket {ticket_id}: {e}")
            return False

    def add_comment(self, ticket_id: str, comment: str, author: str = "system") -> bool:
        """
        Add comment to ticket.

        Args:
            ticket_id: Ticket ID
            comment: Comment text
            author: Comment author

        Returns:
            True if successful
        """
        try:
            # For now, append to details
            # In future, create separate comments table
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT details FROM tickets WHERE ticket_id = ?
                """,
                    (ticket_id,),
                )
                result = cursor.fetchone()

            if not result:
                return False

            current_details = dict(result)["details"] or ""
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_comment = f"\n[{timestamp}] {author}: {comment}"
            updated_details = current_details + new_comment

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tickets 
                    SET details = ?, updated_at = ?
                    WHERE ticket_id = ?
                """,
                    (updated_details, datetime.now().isoformat(), ticket_id),
                )

            logger.info(f"Added comment to ticket {ticket_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding comment to ticket {ticket_id}: {e}")
            return False

    def get_statistics(self, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get ticket statistics.

        Args:
            customer_id: Customer ID (optional, for customer-specific stats)

        Returns:
            Dictionary with statistics
        """
        try:
            query = "SELECT status, priority, COUNT(*) as count FROM tickets"
            params = []

            if customer_id:
                query += " WHERE customer_id = ?"
                params.append(customer_id)

            query += " GROUP BY status, priority"

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()

            stats = {"by_status": {}, "by_priority": {}, "total": 0}

            for row in results:
                data = dict(row)
                status = data["status"]
                priority = data["priority"]
                count = data["count"]

                stats["by_status"][status] = stats["by_status"].get(status, 0) + count
                stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + count
                stats["total"] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting ticket statistics: {e}")
            return {"by_status": {}, "by_priority": {}, "total": 0}

    def count_open_tickets(self, customer_id: Optional[str] = None) -> int:
        """
        Count open tickets.

        Args:
            customer_id: Customer ID (optional)

        Returns:
            Number of open tickets
        """
        try:
            query = "SELECT COUNT(*) as count FROM tickets WHERE status = 'open'"
            params = []

            if customer_id:
                query += " AND customer_id = ?"
                params.append(customer_id)

            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()

            return dict(result)["count"]

        except Exception as e:
            logger.error(f"Error counting open tickets: {e}")
            return 0

    def _add_history(
        self, customer_id: str, event_type: str, details: str, ticket_id: Optional[str] = None
    ) -> None:
        """Add entry to customer history."""
        try:
            history_id = f"HIST{uuid.uuid4().hex[:8].upper()}"

            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO customer_history (
                        history_id,
                        customer_id,
                        event_type,
                        event_date,
                        details,
                        related_ticket_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        history_id,
                        customer_id,
                        event_type,
                        datetime.now().isoformat(),
                        details,
                        ticket_id,
                    ),
                )
        except Exception as e:
            logger.error(f"Error adding history: {e}")
