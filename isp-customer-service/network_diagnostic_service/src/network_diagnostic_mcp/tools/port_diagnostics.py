"""
Port Diagnostics Tools
Check network port status and switch information
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def check_port_status(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Check network port status for customer.
    
    Args:
        db: Database connection
        customer_id: Customer ID
        
    Returns:
        Port status information
    """
    logger.info(f"Checking port status for customer: {customer_id}")
    
    try:
        # Get customer's equipment with MAC addresses
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT equipment_id, equipment_type, mac_address, model
                FROM customer_equipment
                WHERE customer_id = ? AND status = 'active'
            """, (customer_id,))
            
            equipment_list = [dict(row) for row in cursor.fetchall()]
        
        if not equipment_list:
            return {
                "success": False,
                "error": "no_equipment",
                "message": "Klientas neturi užregistruotos aktyvios įrangos"
            }
        
        # Find ports connected to customer's equipment
        ports_info = []
        
        for equipment in equipment_list:
            mac_address = equipment.get("mac_address")
            
            if not mac_address:
                continue
            
            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        p.port_id,
                        p.port_number,
                        p.status,
                        p.speed_mbps,
                        p.duplex,
                        p.vlan_id,
                        p.last_status_change,
                        p.last_checked,
                        s.switch_name,
                        s.location,
                        s.switch_id
                    FROM ports p
                    JOIN switches s ON p.switch_id = s.switch_id
                    WHERE p.equipment_mac = ?
                """, (mac_address,))
                
                port_result = cursor.fetchone()
            
            if port_result:
                port_data = dict(port_result)
                port_data["connected_equipment"] = equipment
                ports_info.append(port_data)
        
        if not ports_info:
            return {
                "success": False,
                "error": "no_port_found",
                "message": "Nerastas tinklo portas klientui",
                "equipment": equipment_list
            }
        
        # Analyze port status
        all_ports_up = all(port["status"] == "up" for port in ports_info)
        
        # Port diagnostics summary
        diagnostics = {
            "total_ports": len(ports_info),
            "ports_up": sum(1 for p in ports_info if p["status"] == "up"),
            "ports_down": sum(1 for p in ports_info if p["status"] == "down"),
            "all_ports_healthy": all_ports_up
        }
        
        logger.info(f"Port check complete: {diagnostics['ports_up']}/{diagnostics['total_ports']} ports up")
        
        return {
            "success": True,
            "ports": ports_info,
            "diagnostics": diagnostics,
            "message": "Visi portai veikia teisingai" if all_ports_up else "Aptikti neaktyvūs portai"
        }
        
    except Exception as e:
        logger.error(f"Error checking port status: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


def get_switch_info(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Get network switch information for customer.
    
    Args:
        db: Database connection
        customer_id: Customer ID
        
    Returns:
        Switch information
    """
    logger.info(f"Getting switch info for customer: {customer_id}")
    
    try:
        # Find switch via customer's port
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT
                    s.switch_id,
                    s.switch_name,
                    s.location,
                    s.ip_address,
                    s.model,
                    s.status,
                    s.max_ports,
                    s.last_checked
                FROM switches s
                JOIN ports p ON s.switch_id = p.switch_id
                WHERE p.customer_id = ?
            """, (customer_id,))
            
            switch_result = cursor.fetchone()
        
        if not switch_result:
            return {
                "success": False,
                "error": "no_switch_found",
                "message": "Nerastas tinklo komutatorius šiam klientui"
            }
        
        switch_data = dict(switch_result)
        
        # Get port usage statistics for this switch
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_ports,
                    SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) as active_ports,
                    SUM(CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END) as assigned_ports
                FROM ports
                WHERE switch_id = ?
            """, (switch_data["switch_id"],))
            
            stats = dict(cursor.fetchone())
        
        switch_data["port_statistics"] = stats
        
        # Calculate health score
        if stats["total_ports"] > 0:
            utilization = (stats["assigned_ports"] / switch_data["max_ports"]) * 100
            active_rate = (stats["active_ports"] / stats["total_ports"]) * 100
            
            switch_data["health"] = {
                "utilization_percent": round(utilization, 1),
                "active_rate_percent": round(active_rate, 1),
                "status": switch_data["status"]
            }
        
        logger.info(f"Switch info retrieved: {switch_data['switch_name']}")
        
        return {
            "success": True,
            "switch": switch_data
        }
        
    except Exception as e:
        logger.error(f"Error getting switch info: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }


def get_port_history(db: DatabaseConnection, port_id: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get port status change history.
    
    Args:
        db: Database connection
        port_id: Port ID
        limit: Number of recent changes
        
    Returns:
        Port history
    """
    logger.info(f"Getting port history for: {port_id}")
    
    try:
        # Note: This would require a port_history table in production
        # For now, return current status
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM ports
                WHERE port_id = ?
            """, (port_id,))
            
            result = cursor.fetchone()
        
        if not result:
            return {
                "success": False,
                "error": "port_not_found",
                "message": f"Portas {port_id} nerastas"
            }
        
        port_data = dict(result)
        
        return {
            "success": True,
            "port": port_data,
            "message": "Istoriniai duomenys nėra saugomi (būsima funkcija)"
        }
        
    except Exception as e:
        logger.error(f"Error getting port history: {e}", exc_info=True)
        return {
            "success": False,
            "error": "database_error",
            "message": f"Klaida: {str(e)}"
        }