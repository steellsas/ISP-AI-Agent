"""
Ticket Management Tools
Create and manage support tickets
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import uuid

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def generate_ticket_id() -> str:
    """Generate unique ticket ID."""
    return f"TKT{uuid.uuid4().hex[:8].upper()}"


def create_ticket(db: DatabaseConnection, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new support ticket.
    
    Args:
        db: Database connection
        args: Ticket parameters
        
    Returns:
        Created ticket data
    """
    customer_id = args.get("customer_id")
    ticket_type = args.get("ticket_type")
    priority = args.get("priority", "medium")
    summary = args.get("summary")
    details = args.get("details", "")
    troubleshooting_steps = args.get("troubleshooting_steps", "")
    
    logger.info(f"Creating ticket for customer {customer_id}: {ticket_type} - {summary}")
    
    try:
        # Verify customer exists
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT customer_id, first_name, last_name 
                FROM customers 
                WHERE customer_id = ?
            """, (customer_id,))
            customer = cursor.fetchone()
        
        if not customer:
            return {
                "success": False,
                "error": "customer_not_found",
                "message": f"Klientas {customer_id} nerastas"
            }
        
        # Generate ticket ID
        ticket_id = generate_ticket_id()
        
        # Create ticket
        with db.cursor() as cursor:
            cursor.execute("""
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
            """, (
                ticket_id,
                customer_id,
                ticket_type,
                priority,
                "open",
                summary,
                details,
                troubleshooting_steps,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
        
        # Create history entry
        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO customer_history (
                    history_id,
                    customer_id,
                    event_type,
                    event_date,
                    details,
                    related_ticket_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                f"HIST{uuid.uuid4().hex[:8].upper()}",
                customer_id,
                "ticket_created",
                datetime.now().isoformat(),
                f"Ticket created: {summary}",
                ticket_id
            ))
        
        logger.info(f"Created ticket {ticket_id} for customer {customer_id}")
        
        return {
            "success": True,
            "ticket": {
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "ticket_type": ticket_type,
                "priority": priority,
                "status": "open",
                "summary": summary,
                "details": details,
                "created_at": datetime.now().isoformat()
            },
            "message": f"Gedimo pranešimas {ticket_id} sėkmingai sukurtas"
        }
        
    except Exception as e:
        logger.error(f"Error in create_ticket: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida kuriant gedimo pranešimą: {str(e)}"
        }


def get_customer_tickets(
    db: DatabaseConnection,
    customer_id: str,
    status: str = "all"
) -> Dict[str, Any]:
    """
    Get customer's tickets.
    
    Args:
        db: Database connection
        customer_id: Customer ID
        status: Filter by status (open, in_progress, closed, all)
        
    Returns:
        List of tickets
    """
    logger.info(f"Getting tickets for customer {customer_id}, status: {status}")
    
    try:
        query = """
            SELECT 
                ticket_id,
                ticket_type,
                priority,
                status,
                summary,
                details,
                created_at,
                updated_at,
                resolved_at,
                troubleshooting_steps
            FROM tickets
            WHERE customer_id = ?
        """
        
        params = [customer_id]
        
        if status != "all":
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC"
        
        with db.cursor() as cursor:
            cursor.execute(query, params)
            tickets = [dict(row) for row in cursor.fetchall()]
        
        # Statistics
        stats = {
            "total": len(tickets),
            "by_status": {},
            "by_priority": {}
        }
        
        for ticket in tickets:
            # Count by status
            t_status = ticket["status"]
            stats["by_status"][t_status] = stats["by_status"].get(t_status, 0) + 1
            
            # Count by priority
            t_priority = ticket["priority"]
            stats["by_priority"][t_priority] = stats["by_priority"].get(t_priority, 0) + 1
        
        return {
            "success": True,
            "tickets": tickets,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Error in get_customer_tickets: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


def update_ticket_status(
    db: DatabaseConnection,
    ticket_id: str,
    status: str,
    resolution_summary: str = None
) -> Dict[str, Any]:
    """
    Update ticket status.
    
    Args:
        db: Database connection
        ticket_id: Ticket ID
        status: New status
        resolution_summary: Resolution summary (for closed tickets)
        
    Returns:
        Updated ticket data
    """
    logger.info(f"Updating ticket {ticket_id} status to: {status}")
    
    try:
        # Check if ticket exists
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT ticket_id, customer_id, status 
                FROM tickets 
                WHERE ticket_id = ?
            """, (ticket_id,))
            ticket = cursor.fetchone()
        
        if not ticket:
            return {
                "success": False,
                "error": "ticket_not_found",
                "message": f"Gedimo pranešimas {ticket_id} nerastas"
            }
        
        ticket_dict = dict(ticket)
        
        # Update ticket
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
        
        with db.cursor() as cursor:
            cursor.execute(update_query, params)
        
        # Create history entry
        if status == "closed":
            with db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_history (
                        history_id,
                        customer_id,
                        event_type,
                        event_date,
                        details,
                        related_ticket_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    f"HIST{uuid.uuid4().hex[:8].upper()}",
                    ticket_dict["customer_id"],
                    "ticket_resolved",
                    datetime.now().isoformat(),
                    f"Ticket resolved: {resolution_summary or 'No details'}",
                    ticket_id
                ))
        
        return {
            "success": True,
            "ticket_id": ticket_id,
            "old_status": ticket_dict["status"],
            "new_status": status,
            "message": f"Gedimo pranešimas {ticket_id} atnaujintas"
        }
        
    except Exception as e:
        logger.error(f"Error in update_ticket_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }