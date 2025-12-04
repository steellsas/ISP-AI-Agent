"""
Network Diagnostics Service - Direct integration with network_diagnostic_service tools
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent.parent.parent
network_service_path = project_root / "network_diagnostic_service" / "src"
shared_path = project_root / "shared" / "src"

for p in [str(network_service_path), str(shared_path)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from database import init_database
from network_diagnostic_mcp.tools.outage_checks import check_customer_affected_by_outage
from network_diagnostic_mcp.tools.port_diagnostics import check_port_status
from network_diagnostic_mcp.tools.connectivity_tests import check_ip_assignment, ping_test
from utils import get_logger

logger = get_logger(__name__)

# Database path
DB_PATH = project_root / "database" / "isp_database.db"

# Cached DB connection (same as CRM)
_db = None


def get_db():
    """Get or create database connection."""
    global _db
    if _db is None:
        logger.info(f"Initializing network diagnostics database: {DB_PATH}")
        _db = init_database(DB_PATH)
    return _db


def check_provider_issues(customer_id: str) -> dict:
    """
    Check for provider-side issues.

    Only CRITICAL provider issues (like area outages) are flagged as provider_issue.
    Other issues (port down, no IP) may be customer-side and need troubleshooting.

    Args:
        customer_id: Customer ID

    Returns:
        Diagnostics results with:
        - provider_issue: bool (only for CRITICAL issues like outages)
        - needs_troubleshooting: bool (for unclear issues)
        - issues_found: list of detected issues
    """
    logger.info(f"Running provider diagnostics for customer: {customer_id}")
    db = get_db()

    results = {
        "customer_id": customer_id,
        "checks_performed": [],
        "issues_found": [],
        "provider_issue": False,  # Only for CRITICAL provider issues
        "needs_troubleshooting": False,  # For issues that need investigation
    }

    # Check 1: Area outages (CRITICAL - definitely provider issue)
    try:
        outage_result = check_customer_affected_by_outage(db, customer_id)
        results["checks_performed"].append("area_outages")
        results["area_outage_check"] = outage_result

        if outage_result.get("affected"):
            results["provider_issue"] = True  # CRITICAL
            results["issues_found"].append(
                {
                    "type": "area_outage",
                    "severity": "critical",
                    "source": "provider",
                    "message": outage_result.get("message"),
                    "outages": outage_result.get("outages", []),
                }
            )
    except Exception as e:
        logger.error(f"Area outage check failed: {e}")
        results["checks_performed"].append("area_outages_failed")

    # Check 2: Port status (may be customer side - router off, cable unplugged)
    try:
        port_result = check_port_status(db, customer_id)
        results["checks_performed"].append("port_status")
        results["port_status_check"] = port_result

        if port_result.get("success"):
            diagnostics = port_result.get("diagnostics", {})
            if not diagnostics.get("all_ports_healthy"):
                results["needs_troubleshooting"] = True
                results["issues_found"].append(
                    {
                        "type": "port_down",
                        "severity": "high",
                        "source": "unknown",  # Could be customer or provider
                        "message": "Tinklo portas neaktyvus (gali būti išjungta įranga)",
                        "ports": port_result.get("ports", []),
                    }
                )
    except Exception as e:
        logger.error(f"Port status check failed: {e}")
        results["checks_performed"].append("port_status_failed")

    # Check 3: IP assignment (may be customer side - equipment off)
    try:
        ip_result = check_ip_assignment(db, customer_id)
        results["checks_performed"].append("ip_assignment")
        results["ip_assignment_check"] = ip_result

        if not ip_result.get("success") or ip_result.get("active_count", 0) == 0:
            results["needs_troubleshooting"] = True
            results["issues_found"].append(
                {
                    "type": "no_ip",
                    "severity": "high",
                    "source": "unknown",  # Could be customer or provider
                    "message": "Nėra aktyvaus IP priskyrimo (gali būti išjungta įranga)",
                }
            )
    except Exception as e:
        logger.error(f"IP assignment check failed: {e}")
        results["checks_performed"].append("ip_assignment_failed")

    logger.info(
        f"Diagnostics complete. Provider issue: {results['provider_issue']}, "
        f"Needs troubleshooting: {results['needs_troubleshooting']}, "
        f"Issues found: {len(results['issues_found'])}"
    )

    return results


def run_ping_test(customer_id: str) -> dict:
    """
    Run connectivity test (ping).

    Args:
        customer_id: Customer ID

    Returns:
        Ping test results
    """
    logger.info(f"Running ping test for customer: {customer_id}")
    db = get_db()

    try:
        return ping_test(db, customer_id)
    except Exception as e:
        logger.error(f"Ping test failed: {e}")
        return {
            "success": False,
            "error": "test_failed",
            "message": f"Nepavyko atlikti testo: {str(e)}",
        }


def get_port_info(customer_id: str) -> dict:
    """
    Get detailed port information.

    Args:
        customer_id: Customer ID

    Returns:
        Port information
    """
    logger.info(f"Getting port info for customer: {customer_id}")
    db = get_db()

    try:
        return check_port_status(db, customer_id)
    except Exception as e:
        logger.error(f"Get port info failed: {e}")
        return {
            "success": False,
            "error": "query_failed",
            "message": f"Nepavyko gauti porto informacijos: {str(e)}",
        }


def get_ip_info(customer_id: str) -> dict:
    """
    Get IP assignment information.

    Args:
        customer_id: Customer ID

    Returns:
        IP assignment info
    """
    logger.info(f"Getting IP info for customer: {customer_id}")
    db = get_db()

    try:
        return check_ip_assignment(db, customer_id)
    except Exception as e:
        logger.error(f"Get IP info failed: {e}")
        return {
            "success": False,
            "error": "query_failed",
            "message": f"Nepavyko gauti IP informacijos: {str(e)}",
        }
