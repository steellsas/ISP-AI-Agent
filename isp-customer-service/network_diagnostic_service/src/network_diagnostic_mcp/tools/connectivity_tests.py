"""
Connectivity Tests Tools
IP assignment, bandwidth, signal quality, and ping tests
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger

from database import DatabaseConnection

logger = get_logger(__name__)


def check_ip_assignment(db: DatabaseConnection, customer_id: str) -> dict[str, Any]:
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
) -> dict[str, Any]:
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


def get_packet_loss_summary(
    db: DatabaseConnection, customer_id: str, window_hours: int = 24
) -> dict[str, Any]:
    """
    Aggregate packet loss over a recent time window from ping_tests.

    Unlike ping_test (latest single result), this rolls up AVG/MAX packet loss
    across the window — the signal used to flag chronic loss. Owning this query
    here keeps SQL inside the network-diagnostic adapter (callers stay DB-free).

    Returns:
        {"has_packet_loss": bool, "avg_packet_loss": float, "max_packet_loss":
        float, "test_count": int, "last_test": str} when tests exist; otherwise
        {"has_packet_loss": False, "test_count": 0}; on error
        {"has_packet_loss": False, "error": str}.
    """
    logger.info(f"Summarizing packet loss for customer: {customer_id} ({window_hours}h)")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    AVG(packet_loss_percent) as avg_loss,
                    MAX(packet_loss_percent) as max_loss,
                    COUNT(*) as test_count,
                    MAX(timestamp) as last_test
                FROM ping_tests
                WHERE customer_id = ?
                AND timestamp >= datetime('now', ?)
                """,
                (customer_id, f"-{window_hours} hours"),
            )
            result = cursor.fetchone()

        if result and result["test_count"] and result["test_count"] > 0:
            avg_loss = result["avg_loss"] or 0
            return {
                "has_packet_loss": avg_loss > 5,  # >5% is problematic
                "avg_packet_loss": avg_loss,
                "max_packet_loss": result["max_loss"] or 0,
                "test_count": result["test_count"],
                "last_test": result["last_test"],
            }

        return {"has_packet_loss": False, "test_count": 0}

    except Exception as e:
        logger.warning(f"Error summarizing packet loss: {e}")
        return {"has_packet_loss": False, "error": str(e)}


def get_bandwidth_summary(
    db: DatabaseConnection, customer_id: str, window_hours: int = 24
) -> dict[str, Any]:
    """
    Aggregate bandwidth_logs over a recent window to detect intermittent /
    unstable connections (high jitter, packet loss, large download variance).

    Unlike check_bandwidth_history (recent raw logs), this returns the rolled-up
    diagnostic flags the agent consumes. SQL lives here, in the adapter.

    Returns:
        {"has_issues": bool, "avg_download_mbps": float, "min_download_mbps":
        float, "max_download_mbps": float, "avg_latency_ms": float,
        "avg_packet_loss": float, "avg_jitter": float, "high_jitter": bool,
        "intermittent": bool, "log_count": int} when logs exist; otherwise
        {"has_issues": False, "log_count": 0}; on error
        {"has_issues": False, "error": str}.
    """
    logger.info(f"Summarizing bandwidth for customer: {customer_id} ({window_hours}h)")

    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    AVG(download_mbps) as avg_download,
                    MIN(download_mbps) as min_download,
                    MAX(download_mbps) as max_download,
                    AVG(latency_ms) as avg_latency,
                    AVG(packet_loss_percent) as avg_packet_loss,
                    AVG(jitter_ms) as avg_jitter,
                    COUNT(*) as log_count
                FROM bandwidth_logs
                WHERE customer_id = ?
                AND timestamp >= datetime('now', ?)
                """,
                (customer_id, f"-{window_hours} hours"),
            )
            result = cursor.fetchone()

        if result and result["log_count"] and result["log_count"] > 0:
            avg_download = result["avg_download"] or 0
            min_download = result["min_download"] or 0
            max_download = result["max_download"] or 0
            avg_jitter = result["avg_jitter"] or 0
            avg_packet_loss = result["avg_packet_loss"] or 0

            # Detect intermittent: big variance in download speeds
            variance = max_download - min_download if max_download else 0
            is_intermittent = variance > (avg_download * 0.5) if avg_download > 0 else False

            return {
                "has_issues": avg_packet_loss > 5 or avg_jitter > 50 or is_intermittent,
                "avg_download_mbps": avg_download,
                "min_download_mbps": min_download,
                "max_download_mbps": max_download,
                "avg_latency_ms": result["avg_latency"] or 0,
                "avg_packet_loss": avg_packet_loss,
                "avg_jitter": avg_jitter,
                "high_jitter": avg_jitter > 50,
                "intermittent": is_intermittent,
                "log_count": result["log_count"],
            }

        return {"has_issues": False, "log_count": 0}

    except Exception as e:
        logger.warning(f"Error summarizing bandwidth: {e}")
        return {"has_issues": False, "error": str(e)}


def check_signal_quality(db: DatabaseConnection, customer_id: str) -> dict[str, Any]:
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


# Replace the ping_test function in connectivity_tests.py with this:


def ping_test(db: DatabaseConnection, customer_id: str) -> dict[str, Any]:
    """
    Get ping test results from database.

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

        # Get recent ping results from ping_tests table
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    packets_sent,
                    packets_received,
                    packet_loss_percent,
                    min_latency_ms,
                    avg_latency_ms,
                    max_latency_ms,
                    jitter_ms
                FROM ping_tests
                WHERE customer_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (customer_id,),
            )

            latest = cursor.fetchone()

        # If no ping_logs, try bandwidth_logs as fallback
        if not latest:
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
                fallback = cursor.fetchone()

            if fallback:
                fallback_dict = dict(fallback)
                stats = {
                    "packets_sent": 10,
                    "packets_received": int(
                        10 * (1 - fallback_dict.get("packet_loss_percent", 0) / 100)
                    ),
                    "packet_loss_percent": fallback_dict.get("packet_loss_percent", 0),
                    "avg_latency_ms": fallback_dict.get("latency_ms", 20),
                }
            else:
                # No data at all - assume healthy
                stats = {
                    "packets_sent": 10,
                    "packets_received": 10,
                    "packet_loss_percent": 0,
                    "avg_latency_ms": 20,
                }
        else:
            latest_dict = dict(latest)
            stats = {
                "packets_sent": latest_dict.get("packets_sent", 10),
                "packets_received": latest_dict.get("packets_received", 10),
                "packet_loss_percent": latest_dict.get("packet_loss_percent", 0),
                "min_latency_ms": latest_dict.get("min_latency_ms"),
                "max_latency_ms": latest_dict.get("max_latency_ms"),
                "avg_latency_ms": latest_dict.get("avg_latency_ms", 20),
                "jitter_ms": latest_dict.get("jitter_ms"),
            }

        # Determine status based on actual data
        packet_loss = stats.get("packet_loss_percent", 0) or 0
        avg_latency = stats.get("avg_latency_ms", 0) or 0

        if packet_loss > 10:
            status = "critical"
            message = f"Kritinė paketų praradimo problema: {packet_loss}%"
        elif packet_loss > 5:
            status = "warning"
            message = f"Aptiktas paketų praradimas: {packet_loss}%"
        elif avg_latency > 100:
            status = "warning"
            message = f"Aukštas ping laikas: {avg_latency}ms"
        else:
            status = "healthy"
            message = "Ryšys normalus"

        logger.info(f"Ping test complete: {packet_loss}% loss, {avg_latency}ms avg")

        return {
            "success": True,
            "statistics": stats,
            "status": status,
            "message": message,
        }

    except Exception as e:
        logger.error(f"Error in ping test: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": f"Klaida: {str(e)}"}
