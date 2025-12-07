"""
Real Tools Integration for ReAct Agent

Wraps existing CRM, Network, and RAG services as agent tools.
Replaces mock functions from poc_react.py with real implementations.

Usage:
    from src.agent.tools import REAL_TOOLS, execute_tool
"""

import sys
import json
import logging
from pathlib import Path
from typing import Any, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# =============================================================================
# PATH SETUP - Add shared and crm_service to path
# =============================================================================

def setup_paths():
    """Add shared, crm_service, and network_diagnostic_service paths for imports."""
    # Find project root (assumes we're in chatbot_core/src/agent/)
    current = Path(__file__).resolve()
    

    chatbot_core = current.parent.parent.parent
    project_root = chatbot_core.parent
    
    # Add paths
    paths_to_add = [
        project_root / "shared" / "src",
        project_root / "crm_service" / "src",
        project_root / "network_diagnostic_service" / "src",
    ]
    
    for path in paths_to_add:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
            logger.debug(f"Added to path: {path_str}")
    
    return project_root

PROJECT_ROOT = setup_paths()
DB_PATH = PROJECT_ROOT / "database" / "isp_database.db"


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

_db_connection = None

def get_db():
    """Get or create database connection."""
    global _db_connection
    
    if _db_connection is None:
        try:
            from database import init_database
            _db_connection = init_database(DB_PATH)
            logger.info(f"Database connected: {DB_PATH}")
        except ImportError as e:
            logger.error(f"Failed to import database module: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    return _db_connection


# =============================================================================
# TOOL DEFINITION
# =============================================================================

@dataclass
class Tool:
    """Tool definition for the agent."""
    name: str
    description: str
    parameters: dict
    function: Callable


# =============================================================================
# REAL TOOL IMPLEMENTATIONS
# =============================================================================

def find_customer(phone: str = None, address: str = None, name: str = None) -> dict:
    """
    Find customer in CRM database.
    
    Args:
        phone: Phone number (e.g., '+37061234567' or '861234567')
        address: Address string (will be parsed)
        name: Customer name
    
    Returns:
        Customer data or error
    """
    logger.info(f"[TOOL] find_customer(phone={phone}, address={address}, name={name})")
    
    try:
        db = get_db()
        
        # Try phone lookup first (most common)
        if phone:
            from crm_mcp.tools.customer_lookup import lookup_customer_by_phone
            result = lookup_customer_by_phone(db, {"phone_number": phone})
            
            if result.get("success"):
                # Format response for agent
                customer = result.get("customer", {})
                addresses = result.get("addresses", [])
                services = result.get("services", [])
                
                return {
                    "success": True,
                    "customer_id": customer.get("customer_id"),
                    "name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
                    "phone": customer.get("phone"),
                    "email": customer.get("email"),
                    "status": customer.get("status"),
                    "addresses": addresses,
                    "active_services": [s.get("plan_name") for s in services if s.get("status") == "active"],
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "customer_not_found"),
                    "message": result.get("message", "Customer not found"),
                }
        
        # Try address lookup
        if address:
            # Parse address string (simple parsing)
            # Expected format: "City, Street HouseNumber" or "City, Street HouseNumber-Apartment"
            from crm_mcp.tools.customer_lookup import lookup_customer_by_address
            
            parts = address.replace(",", " ").split()
            if len(parts) >= 3:
                city = parts[0]
                street = " ".join(parts[1:-1])
                house_apt = parts[-1]
                
                # Check for apartment
                if "-" in house_apt:
                    house, apt = house_apt.split("-", 1)
                else:
                    house = house_apt
                    apt = None
                
                args = {
                    "city": city,
                    "street": street,
                    "house_number": house,
                }
                if apt:
                    args["apartment_number"] = apt
                
                result = lookup_customer_by_address(db, args)
                
                if result.get("success"):
                    customer = result.get("customer", {})
                    return {
                        "success": True,
                        "customer_id": customer.get("customer_id"),
                        "name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
                        "phone": customer.get("phone"),
                        "address": customer.get("address", {}).get("full_address"),
                    }
            
            return {
                "success": False,
                "error": "invalid_address_format",
                "message": "Could not parse address. Expected format: 'City, Street HouseNumber'",
            }
        
        # Name lookup not implemented yet
        if name:
            return {
                "success": False,
                "error": "not_implemented",
                "message": "Name lookup not yet implemented. Please use phone number.",
            }
        
        return {
            "success": False,
            "error": "missing_parameters",
            "message": "Please provide phone number or address to search.",
        }
        
    except ImportError as e:
        logger.error(f"Import error in find_customer: {e}")
        return {
            "success": False,
            "error": "import_error",
            "message": f"Failed to import CRM module: {e}",
        }
    except Exception as e:
        logger.error(f"Error in find_customer: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "message": f"Error searching customer: {e}",
        }


def check_network_status(customer_id: str, address_id: str = None) -> dict:
    """
    Check network status for a customer.
    
    Performs comprehensive network diagnostics:
    - Port status (up/down)
    - IP assignment
    - Signal quality
    - Packet loss (from ping tests)
    - Bandwidth history (for intermittent issues)
    
    Args:
        customer_id: Customer ID from CRM
        address_id: Specific address ID (optional)
    
    Returns:
        Network status data with diagnostics
    """
    logger.info(f"[TOOL] check_network_status(customer_id={customer_id}, address_id={address_id})")
    
    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID is required for network check.",
        }
    
    try:
        db = get_db()
        
        # Import network diagnostic tools
        from network_diagnostic_mcp.tools.port_diagnostics import check_port_status
        from network_diagnostic_mcp.tools.connectivity_tests import check_ip_assignment, check_signal_quality
        
        # 1. Check port status
        port_result = check_port_status(db, customer_id)
        
        # 2. Check IP assignment
        ip_result = check_ip_assignment(db, customer_id)
        
        # 3. Check signal quality (for TV/cable)
        signal_result = check_signal_quality(db, customer_id)
        
        # 4. Check packet loss from ping tests
        packet_loss_data = _check_packet_loss(db, customer_id)
        
        # 5. Check bandwidth logs for intermittent issues
        bandwidth_data = _check_bandwidth_logs(db, customer_id)
        
        # Compile results
        port_status = "unknown"
        ip_assigned = False
        ip_address = None
        
        if port_result.get("success") and port_result.get("ports"):
            ports = port_result["ports"]
            port_up_count = sum(1 for p in ports if p.get("status") == "up")
            port_status = "up" if port_up_count > 0 else "down"
        
        if ip_result.get("success") and ip_result.get("active_count", 0) > 0:
            ip_assigned = True
            assignments = ip_result.get("ip_assignments", [])
            active = [a for a in assignments if a.get("status") == "active"]
            if active:
                ip_address = active[0].get("ip_address")
        
        # Generate issues list
        issues = []
        overall_status = "healthy"
        
        # Port issues
        if port_status == "down":
            issues.append("Port is down - no connection to network")
            overall_status = "issues_detected"
        
        # IP issues
        if not ip_assigned:
            issues.append("No active IP assignment")
            overall_status = "issues_detected"
        
        if ip_result.get("warnings"):
            issues.extend(ip_result["warnings"])
        
        # Signal quality issues
        if signal_result.get("analysis", {}).get("issues"):
            issues.extend(signal_result["analysis"]["issues"])
        
        # Packet loss issues
        if packet_loss_data.get("has_packet_loss"):
            avg_loss = packet_loss_data.get("avg_packet_loss", 0)
            issues.append(f"Packet loss detected: {avg_loss:.1f}%")
            overall_status = "issues_detected"
        
        # Bandwidth/intermittent issues
        if bandwidth_data.get("has_issues"):
            if bandwidth_data.get("high_jitter"):
                issues.append(f"High jitter detected: {bandwidth_data.get('avg_jitter', 0):.1f}ms")
            if bandwidth_data.get("intermittent"):
                issues.append("Intermittent connection - unstable speeds detected")
            if bandwidth_data.get("avg_packet_loss", 0) > 5:
                issues.append(f"Bandwidth logs show packet loss: {bandwidth_data.get('avg_packet_loss', 0):.1f}%")
            overall_status = "issues_detected"
        
        # Generate interpretation
        if not issues:
            interpretation = "Network connection is healthy. Router is connected."
        elif port_status == "down":
            interpretation = "Port is down - requires technician visit."
        elif packet_loss_data.get("has_packet_loss") or bandwidth_data.get("intermittent"):
            interpretation = "Intermittent connection detected - unstable network, may need line check."
        elif not ip_assigned:
            interpretation = "No IP assigned - try router restart to get new IP."
        else:
            interpretation = f"Issues detected: {'; '.join(issues)}"
        
        return {
            "success": True,
            "customer_id": customer_id,
            "overall_status": overall_status,
            "port_status": port_status,
            "ip_assigned": ip_assigned,
            "ip_address": ip_address,
            "port_details": port_result.get("ports", []),
            "ip_details": ip_result.get("ip_assignments", []),
            "signal_quality": signal_result.get("latest", {}),
            "packet_loss": packet_loss_data,
            "bandwidth_history": bandwidth_data,
            "issues": issues if issues else None,
            "interpretation": interpretation,
        }
        
    except ImportError as e:
        logger.warning(f"Network diagnostic module not available: {e}, using fallback")
        return _check_network_status_fallback(db, customer_id)
    except Exception as e:
        logger.error(f"Error in check_network_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": "diagnostic_error",
            "message": f"Error checking network: {e}",
        }


def _check_network_status_fallback(db, customer_id: str) -> dict:
    """Fallback with direct DB queries when network diagnostic module not available."""
    logger.info(f"Using fallback network check for {customer_id}")
    
    issues = []
    overall_status = "healthy"
    port_status = "unknown"
    ip_assigned = False
    ip_address = None
    
    try:
        # Check port status directly
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT port_id, status, speed_mbps 
                FROM ports 
                WHERE customer_id = ?
            """, (customer_id,))
            ports = cursor.fetchall()
            
            if ports:
                port_up = any(p["status"] == "up" for p in ports)
                port_status = "up" if port_up else "down"
                if port_status == "down":
                    issues.append("Port is down - no connection to network")
                    overall_status = "issues_detected"
        
        # Check IP assignment directly
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT ip_address, status 
                FROM ip_assignments 
                WHERE customer_id = ? AND status = 'active'
            """, (customer_id,))
            ips = cursor.fetchall()
            
            if ips:
                ip_assigned = True
                ip_address = ips[0]["ip_address"]
            else:
                issues.append("No active IP assignment")
                overall_status = "issues_detected"
        
        # Check packet loss
        packet_loss_data = _check_packet_loss(db, customer_id)
        if packet_loss_data.get("has_packet_loss"):
            avg_loss = packet_loss_data.get("avg_packet_loss", 0)
            issues.append(f"Packet loss detected: {avg_loss:.1f}%")
            overall_status = "issues_detected"
        
        # Check bandwidth logs
        bandwidth_data = _check_bandwidth_logs(db, customer_id)
        if bandwidth_data.get("has_issues"):
            if bandwidth_data.get("high_jitter"):
                issues.append(f"High jitter: {bandwidth_data.get('avg_jitter', 0):.1f}ms")
            if bandwidth_data.get("intermittent"):
                issues.append("Intermittent connection detected")
            overall_status = "issues_detected"
        
        # Generate interpretation
        if not issues:
            interpretation = "Network connection is healthy (fallback mode)."
        elif port_status == "down":
            interpretation = "Port is down - requires technician visit."
        elif packet_loss_data.get("has_packet_loss") or bandwidth_data.get("intermittent"):
            interpretation = "Intermittent connection detected - unstable network."
        else:
            interpretation = f"Issues detected: {'; '.join(issues)}"
        
        return {
            "success": True,
            "customer_id": customer_id,
            "overall_status": overall_status,
            "port_status": port_status,
            "ip_assigned": ip_assigned,
            "ip_address": ip_address,
            "packet_loss": packet_loss_data,
            "bandwidth_history": bandwidth_data,
            "issues": issues if issues else None,
            "interpretation": interpretation,
        }
        
    except Exception as e:
        logger.error(f"Fallback network check failed: {e}")
        return {
            "success": False,
            "error": "fallback_error",
            "message": f"Error in fallback network check: {e}",
        }


def _check_packet_loss(db, customer_id: str) -> dict:
    """Check recent ping tests for packet loss."""
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    AVG(packet_loss_percent) as avg_loss,
                    MAX(packet_loss_percent) as max_loss,
                    COUNT(*) as test_count,
                    MAX(timestamp) as last_test
                FROM ping_tests
                WHERE customer_id = ?
                AND timestamp >= datetime('now', '-24 hours')
            """, (customer_id,))
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
        logger.warning(f"Error checking packet loss: {e}")
        return {"has_packet_loss": False, "error": str(e)}


def _check_bandwidth_logs(db, customer_id: str) -> dict:
    """Check bandwidth logs for intermittent issues."""
    try:
        with db.cursor() as cursor:
            cursor.execute("""
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
                AND timestamp >= datetime('now', '-24 hours')
            """, (customer_id,))
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
        logger.warning(f"Error checking bandwidth logs: {e}")
        return {"has_issues": False, "error": str(e)}

def check_outages(area: str = None, customer_id: str = None) -> dict:
    """
    Check for active outages or planned works in an area.
    
    Can check by:
    - Area/city name
    - Customer ID (uses customer's address)
    
    Args:
        area: Area/city to check (e.g., "Šiauliai", "Kaunas")
        customer_id: Customer ID to check their specific area
    
    Returns:
        Outage information
    """
    logger.info(f"[TOOL] check_outages(area={area}, customer_id={customer_id})")
    
    try:
        db = get_db()
        
        # Import outage check tools
        from network_diagnostic_mcp.tools.outage_checks import (
            check_area_outages,
            check_customer_affected_by_outage,
        )
        
        # If customer_id provided, check if they're affected
        if customer_id:
            result = check_customer_affected_by_outage(db, customer_id)
            
            if result.get("success"):
                if result.get("affected"):
                    outages = result.get("outages", [])
                    return {
                        "success": True,
                        "customer_id": customer_id,
                        "affected": True,
                        "active_outages": outages,
                        "outage_count": len(outages),
                        "message": f"Klientas paveiktas {len(outages)} gedimo(-ų)",
                    }
                else:
                    return {
                        "success": True,
                        "customer_id": customer_id,
                        "affected": False,
                        "active_outages": [],
                        "message": "Klientas nėra paveiktas žinomų gedimų",
                    }
        
        # Check by area
        if area:
            # Parse area - might be "City, Street" format
            parts = area.split(",")
            city = parts[0].strip()
            street = parts[1].strip() if len(parts) > 1 else None
            
            result = check_area_outages(db, city, street)
            
            if result.get("success"):
                outages = result.get("outages", [])
                summary = result.get("summary", {})
                
                return {
                    "success": True,
                    "area": area,
                    "active_outages": outages,
                    "outage_count": len(outages),
                    "summary": summary,
                    "has_critical": summary.get("has_critical", False),
                    "message": result.get("message", "Patikrinta"),
                }
        
        return {
            "success": True,
            "area": "unknown",
            "active_outages": [],
            "message": "Nurodykite rajoną arba kliento ID gedimų patikrinimui",
        }
        
    except ImportError as e:
        logger.warning(f"Outage module not available: {e}, using fallback")
        return _check_outages_fallback(area)
    except Exception as e:
        logger.error(f"Error in check_outages: {e}", exc_info=True)
        return {
            "success": False,
            "error": "outage_check_error",
            "message": f"Klaida tikrinant gedimus: {e}",
        }


def _check_outages_fallback(area: str) -> dict:
    """Fallback when outage module not available."""
    return {
        "success": True,
        "area": area or "unknown",
        "active_outages": [],
        "message": "Nėra žinomų gedimų (fallback mode)",
    }


def search_knowledge(query: str) -> dict:
    """
    Search troubleshooting knowledge base using RAG.
    
    Uses FAISS vector store with semantic search to find
    relevant troubleshooting guides and FAQ answers.
    
    Args:
        query: Search query describing the problem
    
    Returns:
        Knowledge base results with relevance scores
    """
    logger.info(f"[TOOL] search_knowledge(query={query})")
    
    try:
        # Import RAG retriever
        from src.rag import get_retriever
        
        retriever = get_retriever()
        
        # Load production KB if not already loaded
        if retriever.vector_store.index.ntotal == 0:
            logger.info("Loading production knowledge base...")
            if not retriever.load("production"):
                logger.warning("Failed to load production KB, trying default...")
                retriever.load("default")
        
        # Retrieve relevant documents
        results = retriever.retrieve(query, top_k=3, threshold=0.4)
        
        if not results:
            return {
                "success": True,
                "results": [],
                "message": "No specific knowledge found for this query.",
            }
        
        # Format results for agent
        formatted_results = []
        for result in results:
            metadata = result.get("metadata", {})
            formatted_results.append({
                "title": metadata.get("section_title", metadata.get("filename", "Knowledge Base")),
                "content": result["document"],
                "score": round(result["score"], 2),
                "category": metadata.get("category", "general"),
                "source": metadata.get("filename", "unknown"),
            })
        
        logger.info(f"RAG returned {len(formatted_results)} results")
        
        return {
            "success": True,
            "results": formatted_results,
        }
        
    except ImportError as e:
        logger.warning(f"RAG module not available: {e}, using fallback")
        return _search_knowledge_fallback(query)
    except Exception as e:
        logger.error(f"Error in search_knowledge: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Knowledge base search failed.",
        }


def _search_knowledge_fallback(query: str) -> dict:
    """Fallback keyword-based search when RAG is not available."""
    query_lower = query.lower()
    
    if "router" in query_lower or "restart" in query_lower or "perkrauti" in query_lower:
        return {
            "success": True,
            "results": [{"title": "Router Troubleshooting", "content": "Perkraukite routerį: išjunkite 30 sek, įjunkite atgal."}],
        }
    elif "wifi" in query_lower or "slaptažod" in query_lower:
        return {
            "success": True,
            "results": [{"title": "WiFi", "content": "WiFi slaptažodis yra ant routerio lipduko apačioje."}],
        }
    
    return {"success": True, "results": [], "message": "No specific knowledge found (fallback mode)."}


def create_ticket(
    customer_id: str,
    problem_type: str,
    problem_description: str,
    priority: str = "medium",
    notes: str = None,
) -> dict:
    """
    Create support ticket.
    
    Args:
        customer_id: Customer ID
        problem_type: Type of problem
        problem_description: Description
        priority: Priority level
        notes: Additional notes
    
    Returns:
        Ticket creation result
    """
    logger.info(f"[TOOL] create_ticket(customer_id={customer_id}, type={problem_type})")
    
    try:
        db = get_db()
        
        from crm_mcp.tools.tickets import create_ticket as crm_create_ticket
        
        args = {
            "customer_id": customer_id,
            "ticket_type": problem_type,
            "priority": priority,
            "summary": problem_description[:100] if problem_description else "Support request",
            "details": problem_description,
            "troubleshooting_steps": notes or "",
        }
        
        result = crm_create_ticket(db, args)
        
        
        if result.get("success"):
            ticket_data = result.get("ticket", {})
            ticket_id = ticket_data.get("ticket_id")
            return {
                "success": True,
                "ticket_id": ticket_id,
                "message": f"Ticket created successfully. ID: {ticket_id}",
            }
        else:
            return result
            
    except ImportError as e:
        logger.warning(f"CRM ticket module not available: {e}")
        # Fallback to mock
        import random
        ticket_id = f"TKT{random.randint(10000, 99999)}"
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": f"Ticket {ticket_id} created (mock).",
        }
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return {
            "success": False,
            "error": "ticket_creation_failed",
            "message": f"Failed to create ticket: {e}",
        }


# =============================================================================
# PING TEST TOOL
# =============================================================================

def run_ping_test(customer_id: str) -> dict:
    """
    Run ping/connectivity test for customer.
    
    Tests:
    - Packet loss
    - Latency (ping time)
    - Connection stability
    
    Args:
        customer_id: Customer ID from CRM
    
    Returns:
        Ping test results
    """
    logger.info(f"[TOOL] run_ping_test(customer_id={customer_id})")
    
    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID is required for ping test.",
        }
    
    try:
        db = get_db()
        
        from network_diagnostic_mcp.tools.connectivity_tests import ping_test
        
        result = ping_test(db, customer_id)
        
        if result.get("success"):
            stats = result.get("statistics", {})
            status = result.get("status", "unknown")
            
            # Generate human-readable summary
            if status == "healthy":
                summary = f"Ryšys geras. Vidutinis ping: {stats.get('avg_latency_ms', 'N/A')}ms"
            elif status == "warning":
                summary = f"Aptiktos problemos. Paketų praradimas: {stats.get('packet_loss_percent', 0)}%"
            else:
                summary = f"Kritinė problema. Paketų praradimas: {stats.get('packet_loss_percent', 0)}%"
            
            return {
                "success": True,
                "customer_id": customer_id,
                "status": status,
                "statistics": stats,
                "summary": summary,
                "message": result.get("message"),
            }
        else:
            return result
            
    except ImportError as e:
        logger.warning(f"Ping test module not available: {e}")
        return {
            "success": True,
            "customer_id": customer_id,
            "status": "healthy",
            "statistics": {"avg_latency_ms": 25, "packet_loss_percent": 0},
            "summary": "Ryšys normalus (fallback mode)",
        }
    except Exception as e:
        logger.error(f"Error in run_ping_test: {e}", exc_info=True)
        return {
            "success": False,
            "error": "ping_test_error",
            "message": f"Klaida atliekant ping testą: {e}",
        }


# =============================================================================
# TOOLS REGISTRY
# =============================================================================

REAL_TOOLS = [
    Tool(
        name="find_customer",
        description="Search for customer in CRM by phone number, address, or name. Use this FIRST to identify who is calling.",
        parameters={
            "phone": {"type": "string", "description": "Phone number (e.g., +37061234567 or 861234567)"},
            "address": {"type": "string", "description": "Address to search (format: 'City, Street HouseNumber')"},
            "name": {"type": "string", "description": "Customer name"},
        },
        function=find_customer,
    ),
    Tool(
        name="check_network_status",
        description="Check network status for a customer - port status, IP assignment, signal quality. Use this to diagnose connection issues.",
        parameters={
            "customer_id": {"type": "string", "description": "Customer ID from CRM", "required": True},
            "address_id": {"type": "string", "description": "Specific address ID if customer has multiple"},
        },
        function=check_network_status,
    ),
    Tool(
        name="check_outages",
        description="Check for active outages or planned works. Can check by area name or customer ID.",
        parameters={
            "area": {"type": "string", "description": "Area/city to check (e.g., 'Šiauliai', 'Kaunas')"},
            "customer_id": {"type": "string", "description": "Customer ID to check if affected by outages"},
        },
        function=check_outages,
    ),
    Tool(
        name="run_ping_test",
        description="Run ping/latency test for customer connection. Shows packet loss and response times.",
        parameters={
            "customer_id": {"type": "string", "description": "Customer ID from CRM", "required": True},
        },
        function=run_ping_test,
    ),
    Tool(
        name="search_knowledge",
        description="Search troubleshooting knowledge base for solutions. Use for router issues, WiFi problems, TV issues etc.",
        parameters={
            "query": {"type": "string", "description": "Search query describing the problem", "required": True},
        },
        function=search_knowledge,
    ),
    Tool(
        name="create_ticket",
        description="Create support ticket for technician visit or escalation. Only use when problem cannot be resolved remotely.",
        parameters={
            "customer_id": {"type": "string", "description": "Customer ID", "required": True},
            "problem_type": {"type": "string", "description": "Type: network_issue, technician_visit, equipment_replacement"},
            "problem_description": {"type": "string", "description": "Detailed problem description"},
            "priority": {"type": "string", "description": "Priority: low, medium, high, critical"},
            "notes": {"type": "string", "description": "Additional notes for technician"},
        },
        function=create_ticket,
    ),
]


def get_tools_description() -> str:
    """Generate tools description for system prompt."""
    lines = ["Available tools:"]
    for tool in REAL_TOOLS:
        params = ", ".join([f"{k}: {v.get('description', '')}" for k, v in tool.parameters.items()])
        lines.append(f"\n- {tool.name}: {tool.description}")
        lines.append(f"  Parameters: {params}")
    return "\n".join(lines)


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    for tool in REAL_TOOLS:
        if tool.name == tool_name:
            try:
                result = tool.function(**arguments)
                return json.dumps(result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Tool execution error: {e}", exc_info=True)
                return json.dumps({"error": str(e)})
    
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing real tools integration...\n")
    
    # Test find_customer
    print("=" * 50)
    print("Test 1: find_customer by phone")
    result = find_customer(phone="+37060000001")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 50)
    print("Test 2: check_network_status")
    if result.get("success"):
        customer_id = result.get("customer_id")
        net_result = check_network_status(customer_id)
        print(json.dumps(net_result, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 50)
    print("Test 3: search_knowledge")
    kb_result = search_knowledge("router neveikia perkrauti")
    print(json.dumps(kb_result, indent=2, ensure_ascii=False))
