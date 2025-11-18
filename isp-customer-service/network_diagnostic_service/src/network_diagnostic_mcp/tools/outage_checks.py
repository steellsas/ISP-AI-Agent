"""
Outage Checks Tools
Check for area-wide service outages
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def check_area_outages(
    db: DatabaseConnection,
    city: str,
    street: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check for area-wide service outages.
    
    Args:
        db: Database connection
        city: City name
        street: Street name (optional)
        
    Returns:
        Active outages in the area
    """
    logger.info(f"Checking area outages for: {city}" + (f", {street}" if street else ""))
    
    try:
        # Build query
        query = """
            SELECT 
                outage_id,
                city,
                street,
                area_description,
                outage_type,
                severity,
                status,
                reported_at,
                resolved_at,
                estimated_resolution,
                affected_customers,
                description,
                root_cause,
                resolution_notes
            FROM area_outages
            WHERE LOWER(city) = LOWER(?)
                AND status IN ('active', 'investigating')
        """
        
        params = [city]
        
        if street:
            query += " AND (street IS NULL OR LOWER(street) = LOWER(?))"
            params.append(street)
        
        query += " ORDER BY severity DESC, reported_at DESC"
        
        with db.cursor() as cursor:
            cursor.execute(query, params)
            outages = [dict(row) for row in cursor.fetchall()]
        
        if not outages:
            logger.info(f"No active outages in {city}")
            return {
                "success": True,
                "outages": [],
                "message": f"Nėra žinomų gedimų rajone {city}" + (f", {street}" if street else "")
            }
        
        # Categorize outages by type and severity
        by_type = {}
        by_severity = {}
        
        for outage in outages:
            outage_type = outage["outage_type"]
            severity = outage["severity"]
            
            by_type[outage_type] = by_type.get(outage_type, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        # Get total affected customers
        total_affected = sum(
            outage.get("affected_customers", 0) or 0
            for outage in outages
        )
        
        # Find most severe outage
        critical_outages = [o for o in outages if o["severity"] == "critical"]
        
        summary = {
            "total_outages": len(outages),
            "by_type": by_type,
            "by_severity": by_severity,
            "total_affected_customers": total_affected,
            "has_critical": len(critical_outages) > 0
        }
        
        logger.info(f"Found {len(outages)} active outages")
        
        # Generate message
        if critical_outages:
            message = f"DĖMESIO: {len(critical_outages)} kritinis gedimas rajone"
        else:
            message = f"Aptikti {len(outages)} gedimai rajone"
        
        return {
            "success": True,
            "outages": outages,
            "summary": summary,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Error checking area outages: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


def check_customer_affected_by_outage(
    db: DatabaseConnection,
    customer_id: str
) -> Dict[str, Any]:
    """
    Check if customer is affected by any area outages.
    
    Args:
        db: Database connection
        customer_id: Customer ID
        
    Returns:
        Outages affecting customer
    """
    logger.info(f"Checking if customer {customer_id} is affected by outages")
    
    try:
        # Get customer's address
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT city, street
                FROM addresses
                WHERE customer_id = ? AND is_primary = 1
                LIMIT 1
            """, (customer_id,))
            
            address = cursor.fetchone()
        
        if not address:
            return {
                "success": False,
                "error": "no_address",
                "message": "Kliento adresas nerastas"
            }
        
        address_dict = dict(address)
        city = address_dict["city"]
        street = address_dict["street"]
        
        # Check for outages in customer's area
        result = check_area_outages(db, city, street)
        
        if result.get("success") and result.get("outages"):
            # Filter outages by service type
            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT service_type
                    FROM service_plans
                    WHERE customer_id = ? AND status = 'active'
                """, (customer_id,))
                
                services = [dict(row)["service_type"] for row in cursor.fetchall()]
            
            # Check which outages affect customer's services
            affecting_outages = []
            for outage in result["outages"]:
                outage_type = outage["outage_type"]
                if outage_type == "all" or any(
                    svc in outage_type or outage_type in svc
                    for svc in services
                ):
                    affecting_outages.append(outage)
            
            if affecting_outages:
                return {
                    "success": True,
                    "affected": True,
                    "outages": affecting_outages,
                    "customer_services": services,
                    "message": f"Klientas paveiktas {len(affecting_outages)} gedimų"
                }
        
        return {
            "success": True,
            "affected": False,
            "message": "Klientas nėra paveiktas žinomų gedimų"
        }
        
    except Exception as e:
        logger.error(f"Error checking customer outage impact: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


def get_outage_history(
    db: DatabaseConnection,
    city: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get outage history for an area.
    
    Args:
        db: Database connection
        city: City name
        days: Number of days to look back
        
    Returns:
        Outage history
    """
    logger.info(f"Getting outage history for {city} (last {days} days)")
    
    try:
        # Calculate date threshold
        date_threshold = (datetime.now() - timedelta(days=days)).isoformat()
        
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    outage_id,
                    street,
                    outage_type,
                    severity,
                    status,
                    reported_at,
                    resolved_at,
                    affected_customers,
                    description
                FROM area_outages
                WHERE LOWER(city) = LOWER(?)
                    AND reported_at >= ?
                ORDER BY reported_at DESC
            """, (city, date_threshold))
            
            outages = [dict(row) for row in cursor.fetchall()]
        
        if not outages:
            return {
                "success": True,
                "outages": [],
                "message": f"Nėra gedimų istorijos per pastarąsias {days} dienų"
            }
        
        # Calculate statistics
        resolved = [o for o in outages if o["status"] == "resolved"]
        active = [o for o in outages if o["status"] in ["active", "investigating"]]
        
        stats = {
            "total_outages": len(outages),
            "resolved": len(resolved),
            "active": len(active),
            "by_type": {},
            "by_severity": {}
        }
        
        for outage in outages:
            outage_type = outage["outage_type"]
            severity = outage["severity"]
            
            stats["by_type"][outage_type] = stats["by_type"].get(outage_type, 0) + 1
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
        
        return {
            "success": True,
            "outages": outages,
            "statistics": stats,
            "period_days": days,
            "message": f"Rasti {len(outages)} gedimai per {days} dienų"
        }
        
    except Exception as e:
        logger.error(f"Error getting outage history: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


# Import timedelta for outage history
from datetime import timedelta