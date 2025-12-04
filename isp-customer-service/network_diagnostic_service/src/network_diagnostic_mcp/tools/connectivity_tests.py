"""
Connectivity Tests Tools
IP assignment, bandwidth, signal quality, and ping tests
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import random

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from database import DatabaseConnection
from utils import get_logger

logger = get_logger(__name__)


def check_ip_assignment(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Check IP address assignment for customer.

    Args:
        db: Database connection
        customer_id: Customer ID

    Returns:
        IP assignment information
    """
    logger.info(f"Checking IP assignment for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    ip.assignment_id,
                    ip.ip_address,
                    ip.mac_address,
                    ip.assignment_type,
                    ip.assigned_at,
                    ip.lease_expires,
                    ip.status,
                    ip.last_seen
                FROM ip_assignments ip
                WHERE ip.customer_id = ?
                ORDER BY ip.assigned_at DESC
            """,
                (customer_id,),
            )

            assignments = [dict(row) for row in cursor.fetchall()]

        if not assignments:
            return {
                "success": False,
                "error": "no_ip_assignment",
                "message": "Klientui nėra priskirto IP adreso",
            }

        active_ips = [ip for ip in assignments if ip["status"] == "active"]

        # Check for lease expiration
        warnings = []
        for ip in active_ips:
            if ip["assignment_type"] == "dhcp" and ip["lease_expires"]:
                expires = datetime.fromisoformat(ip["lease_expires"])
                if expires < datetime.now():
                    warnings.append(f"DHCP lease expired for {ip['ip_address']}")
                elif expires < datetime.now() + timedelta(hours=24):
                    warnings.append(f"DHCP lease expiring soon for {ip['ip_address']}")

        logger.info(f"Found {len(active_ips)} active IP assignments")

        return {
            "success": True,
            "ip_assignments": assignments,
            "active_count": len(active_ips),
            "warnings": warnings if warnings else None,
            "message": "IP priskirimas aktyvus" if active_ips else "Nėra aktyvių IP priskyrimų",
        }

    except Exception as e:
        logger.error(f"Error checking IP assignment: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def check_bandwidth_history(
    db: DatabaseConnection, customer_id: str, limit: int = 10
) -> Dict[str, Any]:
    """
    Check bandwidth usage history and speed tests.

    Args:
        db: Database connection
        customer_id: Customer ID
        limit: Number of recent measurements

    Returns:
        Bandwidth history
    """
    logger.info(f"Checking bandwidth history for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    log_id,
                    timestamp,
                    download_mbps,
                    upload_mbps,
                    latency_ms,
                    packet_loss_percent,
                    jitter_ms,
                    measurement_type
                FROM bandwidth_logs
                WHERE customer_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (customer_id, limit),
            )

            logs = [dict(row) for row in cursor.fetchall()]

        if not logs:
            return {
                "success": True,
                "bandwidth_logs": [],
                "message": "Nėra bandwidth istorijos duomenų",
            }

        # Calculate statistics
        download_speeds = [log["download_mbps"] for log in logs if log["download_mbps"]]
        upload_speeds = [log["upload_mbps"] for log in logs if log["upload_mbps"]]
        latencies = [log["latency_ms"] for log in logs if log["latency_ms"]]

        stats = {}

        if download_speeds:
            stats["download"] = {
                "avg_mbps": round(sum(download_speeds) / len(download_speeds), 2),
                "min_mbps": min(download_speeds),
                "max_mbps": max(download_speeds),
            }

        if upload_speeds:
            stats["upload"] = {
                "avg_mbps": round(sum(upload_speeds) / len(upload_speeds), 2),
                "min_mbps": min(upload_speeds),
                "max_mbps": max(upload_speeds),
            }

        if latencies:
            stats["latency"] = {
                "avg_ms": round(sum(latencies) / len(latencies), 2),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
            }

        logger.info(f"Found {len(logs)} bandwidth measurements")

        return {
            "success": True,
            "bandwidth_logs": logs,
            "statistics": stats,
            "message": f"Rasti {len(logs)} bandwidth matavimai",
        }

    except Exception as e:
        logger.error(f"Error checking bandwidth history: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def check_signal_quality(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Check TV/Cable signal quality.

    Args:
        db: Database connection
        customer_id: Customer ID

    Returns:
        Signal quality information
    """
    logger.info(f"Checking signal quality for customer: {customer_id}")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    quality_id,
                    timestamp,
                    signal_strength_dbm,
                    snr_db,
                    ber,
                    mer_db,
                    status,
                    channel_issues
                FROM signal_quality
                WHERE customer_id = ?
                ORDER BY timestamp DESC
                LIMIT 10
            """,
                (customer_id,),
            )

            measurements = [dict(row) for row in cursor.fetchall()]

        if not measurements:
            return {
                "success": True,
                "signal_quality": [],
                "message": "Nėra signalo kokybės duomenų (gali būti tik interneto paslauga)",
            }

        latest = measurements[0]

        # Analyze signal quality
        analysis = {"overall_status": latest["status"], "timestamp": latest["timestamp"]}

        issues = []

        if latest["signal_strength_dbm"] and latest["signal_strength_dbm"] < -15:
            issues.append("Silpnas signalo lygis")

        if latest["snr_db"] and latest["snr_db"] < 30:
            issues.append("Žemas SNR (signal-to-noise ratio)")

        if latest["ber"] and latest["ber"] > 0.0001:
            issues.append("Aukštas BER (bit error rate)")

        analysis["issues"] = issues if issues else None

        logger.info(f"Signal quality status: {latest['status']}")

        return {
            "success": True,
            "signal_quality": measurements,
            "latest": latest,
            "analysis": analysis,
            "message": (
                "Signalas normalus" if not issues else f"Aptiktos problemos: {', '.join(issues)}"
            ),
        }

    except Exception as e:
        logger.error(f"Error checking signal quality: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}


def ping_test(db: DatabaseConnection, customer_id: str) -> Dict[str, Any]:
    """
    Perform simulated ping test.

    Note: This is a mock implementation that simulates ping results
    based on customer's recent bandwidth data.

    Args:
        db: Database connection
        customer_id: Customer ID

    Returns:
        Ping test results
    """
    logger.info(f"Performing ping test for customer: {customer_id}")

    try:
        # Check if customer exists and has active service
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM service_plans
                WHERE customer_id = ? AND status = 'active'
            """,
                (customer_id,),
            )

            result = dict(cursor.fetchone())
            if result["count"] == 0:
                return {
                    "success": False,
                    "error": "no_active_service",
                    "message": "Klientas neturi aktyvios paslaugos",
                }

        # Get recent latency from bandwidth logs
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT latency_ms, packet_loss_percent
                FROM bandwidth_logs
                WHERE customer_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (customer_id,),
            )

            latest = cursor.fetchone()

        # Simulate ping results
        if latest:
            latest_dict = dict(latest)
            base_latency = latest_dict.get("latency_ms", 20)
            base_loss = latest_dict.get("packet_loss_percent", 0)
        else:
            base_latency = random.randint(15, 35)
            base_loss = 0

        # Generate 10 ping results with variation
        ping_results = []
        for i in range(10):
            latency = base_latency + random.uniform(-5, 5)
            ping_results.append(
                {
                    "sequence": i + 1,
                    "latency_ms": round(latency, 2),
                    "status": "success" if random.random() > (base_loss / 100) else "timeout",
                }
            )

        successful_pings = [p for p in ping_results if p["status"] == "success"]

        if successful_pings:
            latencies = [p["latency_ms"] for p in successful_pings]
            stats = {
                "packets_sent": 10,
                "packets_received": len(successful_pings),
                "packet_loss_percent": round((10 - len(successful_pings)) / 10 * 100, 1),
                "min_latency_ms": round(min(latencies), 2),
                "max_latency_ms": round(max(latencies), 2),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            }
        else:
            stats = {"packets_sent": 10, "packets_received": 0, "packet_loss_percent": 100.0}

        # Determine status
        if stats["packet_loss_percent"] > 10:
            status = "critical"
            message = "Kritinė paketu praradimo problema"
        elif stats["packet_loss_percent"] > 5:
            status = "warning"
            message = "Aptiktas paketų praradimas"
        elif stats.get("avg_latency_ms", 0) > 100:
            status = "warning"
            message = "Aukštas ping laikas"
        else:
            status = "healthy"
            message = "Ryšys normalus"

        logger.info(
            f"Ping test complete: {stats['packet_loss_percent']}% loss, "
            f"{stats.get('avg_latency_ms', 'N/A')}ms avg"
        )

        return {
            "success": True,
            "ping_results": ping_results,
            "statistics": stats,
            "status": status,
            "message": message,
            "note": "Simuliuotas testas pagal istorinius duomenis",
        }

    except Exception as e:
        logger.error(f"Error in ping test: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}
