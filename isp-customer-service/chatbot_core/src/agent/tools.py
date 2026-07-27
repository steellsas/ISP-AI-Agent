"""
Real Tools Integration for ReAct Agent

Wraps existing CRM, Network, and RAG services as agent tools.
Replaces mock functions from poc_react.py with real implementations.

Usage:
    from src.agent.tools import REAL_TOOLS, execute_tool
"""

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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

    def to_openai_schema(self) -> dict:
        """
        Export this tool as an OpenAI function-calling schema.

        LiteLLM (and the providers behind it: OpenAI, Anthropic, Gemini,
        Ollama) all accept the OpenAI tool schema shape, so this single
        export keeps the `Tool` dataclass as the one source of truth while
        speaking the wire format every model understands.

        Our internal `parameters` shape is::

            {"customer_id": {"type": "string", "description": "...", "required": True}}

        The OpenAI shape splits that into JSON-Schema `properties` (without the
        `required` flag) plus a top-level `required` list of names::

            {
                "type": "function",
                "function": {
                    "name": ...,
                    "description": ...,
                    "parameters": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string", "description": "..."}},
                        "required": ["customer_id"],
                    },
                },
            }
        """
        properties: dict = {}
        required: list[str] = []

        for param_name, spec in self.parameters.items():
            # Copy the spec but strip our internal "required" marker — in
            # JSON Schema requiredness lives in the sibling `required` list,
            # not inside each property.
            prop = {k: v for k, v in spec.items() if k != "required"}
            properties[param_name] = prop

            if spec.get("required"):
                required.append(param_name)

        parameters_schema: dict = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters_schema["required"] = required

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters_schema,
            },
        }

    def validate_arguments(self, arguments: dict) -> tuple[dict, dict | None]:
        """
        Validate and clean model-supplied arguments against this tool's schema.

        Native function calling does not guarantee well-formed arguments — the
        model may hallucinate parameter names, omit required ones, or send the
        wrong scalar type. We validate here, at the single execution choke
        point, using the same `parameters` dict that produces the OpenAI schema
        (one source of truth).

        Policy:
          - Missing required parameter -> hard stop: return a structured error
            (no execution) so the model sees it as a tool result and can
            self-correct on the next turn.
          - Unknown argument -> dropped with a warning (the function would
            reject it as an unexpected kwarg anyway); robust to harmless extra
            keys the model invents.
          - Declared "string" but a scalar (int/float/bool) arrived -> coerced
            to str so downstream code gets the type it expects.

        Returns:
            (cleaned_args, error). On success error is None. On failure
            cleaned_args is {} and error is a JSON-serializable dict describing
            the problem, to be handed back to the model as the observation.
        """
        if not isinstance(arguments, dict):
            return {}, {
                "error": "invalid_arguments",
                "tool": self.name,
                "message": "Arguments must be a JSON object.",
                "valid_parameters": self.parameters,
            }

        cleaned: dict = {}
        unknown: list[str] = []

        for key, value in arguments.items():
            spec = self.parameters.get(key)
            if spec is None:
                unknown.append(key)
                continue
            # Light coercion: schema says string but a scalar slipped through.
            if spec.get("type") == "string" and isinstance(value, (int, float, bool)):
                value = str(value)
            cleaned[key] = value

        if unknown:
            logger.warning(
                f"[TOOL] {self.name}: dropping unknown argument(s): {', '.join(unknown)}"
            )

        missing_required = [
            name
            for name, spec in self.parameters.items()
            if spec.get("required") and name not in cleaned
        ]
        if missing_required:
            return {}, {
                "error": "invalid_arguments",
                "tool": self.name,
                "missing_required": missing_required,
                "valid_parameters": self.parameters,
            }

        return cleaned, None


# =============================================================================
# REAL TOOL IMPLEMENTATIONS
# =============================================================================


def _parse_address(address: str) -> tuple[dict | None, dict | None]:
    """
    Parse a free-form address string into CRM lookup args.

    Expected format: "City, Street HouseNumber" or
    "City, Street HouseNumber-Apartment". Returns (args, error); on a parse
    failure args is None and error is a normalized error payload ready to be
    returned to the agent.
    """
    parts = address.replace(",", " ").split()
    if len(parts) < 3:
        return None, {
            "success": False,
            "error": "invalid_address_format",
            "message": "Could not parse address. Expected format: 'City, Street HouseNumber'",
        }

    city = parts[0]
    street = " ".join(parts[1:-1])
    house_apt = parts[-1]

    if "-" in house_apt:
        house, apt = house_apt.split("-", 1)
    else:
        house, apt = house_apt, None

    args = {"city": city, "street": street, "house_number": house}
    if apt:
        args["apartment_number"] = apt
    return args, None


def _format_customer_profile(details: dict) -> dict:
    """
    Build the normalized find_customer payload from get_customer_details().

    Every find_customer search key (phone / address today, name / account code
    later) resolves to a customer_id and then funnels through this single
    formatter, so the agent always sees an identical shape no matter how the
    customer was found. `addresses` is always a list of structured objects
    (never a bare string), and account fields (status/email) are always
    present so downstream checks (e.g. suspension) work on every path.
    """
    customer = details.get("customer", {})
    addresses = details.get("addresses", [])
    services = details.get("services", [])

    return {
        "success": True,
        "customer_id": customer.get("customer_id"),
        "name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        "phone": customer.get("phone"),
        "email": customer.get("email"),
        "status": customer.get("status"),
        "addresses": [
            {
                "address_id": a.get("address_id"),
                "full_address": a.get("full_address"),
                "city": a.get("city"),
                "street": a.get("street"),
                "house_number": a.get("house_number"),
                "apartment_number": a.get("apartment_number"),
                "is_primary": bool(a.get("is_primary")),
            }
            for a in addresses
        ],
        # get_customer_details already filters to active service plans.
        "active_services": [s.get("plan_name") for s in services if s.get("plan_name")],
    }


def resolve_address(
    city: str = None,
    street: str = None,
    house_number: str = None,
    apartment_number: str = None,
    surname: str = None,
) -> dict:
    """
    Resolve a (possibly partial) spoken address into a customer — rich result.

    Returns a per-level diagnosis (city/street/house/apartment status,
    alternatives, found_elsewhere) plus a `hint` telling the agent what to
    clarify next. On unique success the full normalized customer profile is
    attached (same shape as find_customer).
    """
    logger.info(
        f"[TOOL] resolve_address(city={city!r}, street={street!r}, house={house_number!r}, "
        f"apt={apartment_number!r}, surname={'<given>' if surname else None})"
    )

    try:
        db = get_db()
        from crm_mcp.tools.address_resolver import resolve_address as _resolve
        from crm_mcp.tools.customer_lookup import get_customer_details

        result = _resolve(
            db,
            {
                "city": city,
                "street": street,
                "house_number": house_number,
                "apartment_number": apartment_number,
                "surname": surname,
            },
        )

        # Unique hit -> attach the same normalized profile find_customer returns.
        if result.get("success") and result.get("customer_id"):
            details = get_customer_details(db, result["customer_id"])
            if details.get("success"):
                result["customer"] = _format_customer_profile(details)
        return result

    except ImportError as e:
        logger.error(f"Import error in resolve_address: {e}")
        return {
            "success": False,
            "error": "service_unavailable",
            "message": "Address resolver service is unavailable.",
        }
    except Exception as e:
        logger.error(f"Error in resolve_address: {e}", exc_info=True)
        return {
            "success": False,
            "error": "internal_error",
            "message": f"Error resolving address: {e}",
        }


def find_customer(
    phone: str = None, address: str = None, name: str = None, account_code: str = None
) -> dict:
    """
    Find customer in CRM database.

    A search key (phone / account code / address) only *resolves* a
    customer_id. The full profile is then fetched once by customer_id via
    get_customer_details, so every lookup path returns the same normalized
    shape (see _format_customer_profile).

    Args:
        phone: Phone number (e.g., '+37061234567' or '861234567')
        address: Address string (legacy single-string path; prefer resolve_address)
        name: Customer name (not supported — surname is confirm-only)
        account_code: Invoice account code (abonento kodas), e.g. 'AB-10101'

    Returns:
        Normalized customer profile or error
    """
    # Phone is masked by the central PII log filter; address/name are PII the
    # regex can't catch, so log only whether each lookup path was provided.
    logger.info(
        f"[TOOL] find_customer(phone={phone}, by_address={address is not None}, "
        f"by_name={name is not None}, by_account_code={account_code is not None})"
    )

    try:
        db = get_db()
        from crm_mcp.tools.address_resolver import lookup_customer_by_account_code
        from crm_mcp.tools.customer_lookup import (
            get_customer_details,
            lookup_customer_by_address,
            lookup_customer_by_phone,
        )

        customer_id = None

        # --- Resolve customer_id from whichever search key was provided ----
        if account_code:
            result = lookup_customer_by_account_code(db, account_code)
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "customer_not_found"),
                    "message": result.get("message", "Customer not found"),
                }
            customer_id = result.get("customer", {}).get("customer_id")

        elif phone:
            result = lookup_customer_by_phone(db, {"phone_number": phone})
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "customer_not_found"),
                    "message": result.get("message", "Customer not found"),
                }
            customer_id = result.get("customer", {}).get("customer_id")

        elif address:
            args, parse_error = _parse_address(address)
            if parse_error is not None:
                return parse_error
            result = lookup_customer_by_address(db, args)
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "customer_not_found"),
                    "message": result.get("message", "Customer not found"),
                }
            customer_id = result.get("customer", {}).get("customer_id")

        elif name:
            return {
                "success": False,
                "error": "not_implemented",
                "message": "Name lookup not yet implemented. Please use phone number.",
            }

        else:
            return {
                "success": False,
                "error": "missing_parameters",
                "message": "Please provide phone number or address to search.",
            }

        # --- Single enrichment-by-id path -> identical shape everywhere ----
        details = get_customer_details(db, customer_id)
        if not details.get("success"):
            return {
                "success": False,
                "error": details.get("error", "customer_not_found"),
                "message": details.get("message", "Customer not found"),
            }
        return _format_customer_profile(details)

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


def diagnose_connection(customer_id: str) -> dict:
    """
    Run the full no-internet diagnostic and return a deterministic verdict.

    One call gathers billing + incident + switch + port telemetry + neighbour
    signals and runs the decision tree (see agent/verdict.py). Returns
    {verdict: {side, group, action, reason, agent_message}, signals: {...}}.
    The verdict draws the provider/customer boundary; on side=customer or
    unclear the agent continues the conversation (symptoms + RAG).

    Args:
        customer_id: Customer ID from CRM (identify the customer first)

    Returns:
        Verdict envelope or error
    """
    logger.info(f"[TOOL] diagnose_connection(customer_id={customer_id})")

    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID is required for diagnosis.",
        }

    try:
        from .verdict import diagnose

        return diagnose(get_db(), customer_id)

    except ImportError as e:
        # Same policy as check_network_status: no raw-SQL fallback in the
        # agent layer — if an adapter can't be imported, fail cleanly.
        logger.error(f"Diagnostic modules not available: {e}")
        return {
            "success": False,
            "error": "service_unavailable",
            "message": "Diagnostic service is unavailable.",
        }
    except Exception as e:
        logger.error(f"Error in diagnose_connection: {e}", exc_info=True)
        return {
            "success": False,
            "error": "diagnostic_error",
            "message": f"Error diagnosing connection: {e}",
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

        # Import network diagnostic tools (the agent talks only to the service;
        # all SQL lives in the network-diagnostic adapter, not here).
        from network_diagnostic_mcp.tools.connectivity_tests import (
            check_ip_assignment,
            check_signal_quality,
            get_bandwidth_summary,
            get_packet_loss_summary,
        )
        from network_diagnostic_mcp.tools.port_diagnostics import check_port_status

        # 1. Check port status
        port_result = check_port_status(db, customer_id)

        # 2. Check IP assignment
        ip_result = check_ip_assignment(db, customer_id)

        # 3. Check signal quality (for TV/cable)
        signal_result = check_signal_quality(db, customer_id)

        # 4. Check packet loss from ping tests (24h aggregate)
        packet_loss_data = get_packet_loss_summary(db, customer_id)

        # 5. Check bandwidth logs for intermittent issues (24h aggregate)
        bandwidth_data = get_bandwidth_summary(db, customer_id)

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
                issues.append(
                    f"Bandwidth logs show packet loss: {bandwidth_data.get('avg_packet_loss', 0):.1f}%"
                )
            overall_status = "issues_detected"

        # Generate interpretation
        if not issues:
            interpretation = "Network connection is healthy. Router is connected."
        elif port_status == "down":
            interpretation = "Port is down - requires technician visit."
        elif packet_loss_data.get("has_packet_loss") or bandwidth_data.get("intermittent"):
            interpretation = (
                "Intermittent connection detected - unstable network, may need line check."
            )
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
        # No silent raw-SQL fallback: if the network-diagnostic adapter can't be
        # imported, the agent has no DB-access path of its own (by design). Fail
        # with a clean envelope instead of reaching into the database directly.
        logger.error(f"Network diagnostic module not available: {e}")
        return {
            "success": False,
            "error": "service_unavailable",
            "message": "Network diagnostic service is unavailable.",
        }
    except Exception as e:
        logger.error(f"Error in check_network_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": "diagnostic_error",
            "message": f"Error checking network: {e}",
        }


def update_mac(customer_id: str) -> dict:
    """
    SIMULATED: bind the device currently seen on the customer's line.

    Orchestrates both domains (like diagnose_connection): the network adapter
    re-binds the port to the OBSERVED MAC + refreshes the lease; the CRM
    adapter updates the registered equipment record. Use after the customer
    confirms they replaced the router (B6 foreign MAC), or for the B-Plan
    bridge (cable straight into a PC / customer's own router).

    Args:
        customer_id: Customer ID from CRM

    Returns:
        {success, old_mac, new_mac, message} or error
    """
    logger.info(f"[TOOL] update_mac(customer_id={customer_id})")

    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID is required.",
        }

    try:
        db = get_db()
        from crm_mcp.tools.equipment import update_equipment_mac
        from network_diagnostic_mcp.tools.port_actions import bind_port_mac

        # Network side first — it knows WHAT is observed on the line.
        bind = bind_port_mac(db, customer_id)
        if not bind.get("success"):
            return bind

        # CRM side: keep the equipment registry consistent with the binding.
        crm = update_equipment_mac(db, customer_id, bind["new_mac"])
        if not crm.get("success"):
            logger.warning(f"CRM equipment MAC update failed: {crm.get('error')}")

        return {
            "success": True,
            "customer_id": customer_id,
            "old_mac": bind.get("old_mac"),
            "new_mac": bind.get("new_mac"),
            "message": bind.get("message"),
        }

    except ImportError as e:
        logger.error(f"Port action modules not available: {e}")
        return {
            "success": False,
            "error": "service_unavailable",
            "message": "MAC binding service is unavailable.",
        }
    except Exception as e:
        logger.error(f"Error in update_mac: {e}", exc_info=True)
        return {
            "success": False,
            "error": "action_error",
            "message": f"Error binding MAC: {e}",
        }


def reset_port(customer_id: str) -> dict:
    """
    SIMULATED: bounce the customer's switch port / session.

    Use right after update_mac (forces re-authorization) or when the verdict
    suggests a session freeze.

    Args:
        customer_id: Customer ID from CRM

    Returns:
        {success, port_id, message} or error
    """
    logger.info(f"[TOOL] reset_port(customer_id={customer_id})")

    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID is required.",
        }

    try:
        db = get_db()
        from network_diagnostic_mcp.tools.port_actions import reset_customer_port

        return reset_customer_port(db, customer_id)

    except ImportError as e:
        logger.error(f"Port action modules not available: {e}")
        return {
            "success": False,
            "error": "service_unavailable",
            "message": "Port reset service is unavailable.",
        }
    except Exception as e:
        logger.error(f"Error in reset_port: {e}", exc_info=True)
        return {
            "success": False,
            "error": "action_error",
            "message": f"Error resetting port: {e}",
        }


def simulate_bridge_connect(customer_id: str) -> dict:
    """SIMULATED (demo/test): make the plugged-in bridge device appear on the line.

    Deliberately NOT registered as an agent Tool — the LLM must never invoke it. The
    engine calls it directly (behind SIMULATE_BRIDGE) when the caller confirms plugging a
    PC into the wall cable, so the demo's mock DB reflects the physical action and the
    bridge can VERIFY + bind. In production the real device appears on its own.
    """
    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID required.",
        }
    try:
        db = get_db()
        from network_diagnostic_mcp.tools.port_actions import connect_bridge_device

        return connect_bridge_device(db, customer_id)
    except ImportError as e:
        logger.error(f"Bridge-connect sim unavailable: {e}")
        return {"success": False, "error": "service_unavailable", "message": "unavailable"}
    except Exception as e:
        logger.error(f"Error in simulate_bridge_connect: {e}", exc_info=True)
        return {"success": False, "error": "action_error", "message": f"{e}"}


def simulate_bridge_disconnect(customer_id: str) -> dict:
    """SIMULATED (demo/test): clear the bridge device from the line (undo a plug-in).
    Not a registered Tool — used by the manual test command / re-test setup."""
    if not customer_id:
        return {
            "success": False,
            "error": "missing_customer_id",
            "message": "Customer ID required.",
        }
    try:
        db = get_db()
        from network_diagnostic_mcp.tools.port_actions import disconnect_bridge_device

        return disconnect_bridge_device(db, customer_id)
    except Exception as e:
        logger.error(f"Error in simulate_bridge_disconnect: {e}", exc_info=True)
        return {"success": False, "error": "action_error", "message": f"{e}"}


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
                        "outage_count": 0,
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

                message = result.get("message", "Patikrinta")
                # A city-only check returns outages from OTHER streets too —
                # observed in testing: the model attributed another street's
                # outage to the caller. Make the tool itself raise the flag.
                if outages and not street:
                    message = (
                        "DĖMESIO: tikrinta visame mieste BE gatvės — rasti gedimai "
                        "gali būti KITOSE gatvėse. Prieš informuojant klientą "
                        "PRIVALOMA sutikrinti, ar gedimo gatvė (laukas 'street') "
                        "sutampa su kliento gatve. " + message
                    )

                return {
                    "success": True,
                    "area": area,
                    "affected": len(outages) > 0,
                    "active_outages": outages,
                    "outage_count": len(outages),
                    "summary": summary,
                    "has_critical": summary.get("has_critical", False),
                    "message": message,
                }

        return {
            "success": True,
            "area": "unknown",
            "affected": False,
            "active_outages": [],
            "outage_count": 0,
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
        "affected": False,
        "active_outages": [],
        "outage_count": 0,
        "message": "Nėra žinomų gedimų (fallback mode)",
    }


def search_knowledge(query: str) -> dict:
    """
    Search troubleshooting knowledge base using RAG.

    Uses the FAISS vector store via the HYBRID retriever (semantic cosine +
    keyword blend) — the eval harness measured hybrid ranking strictly better
    than semantic-only (MRR 0.972 vs 0.917), so production uses it. Retrieval
    knobs come from config (rag_top_k / rag_threshold), not hardcoded here.

    Args:
        query: Search query describing the problem

    Returns:
        Knowledge base results with relevance scores
    """
    logger.info(f"[TOOL] search_knowledge(query={query})")

    try:
        # Import RAG retriever (hybrid = semantic + keyword)
        from src.rag import get_hybrid_retriever

        retriever = get_hybrid_retriever()

        # Load production KB if not already loaded
        if not retriever.is_loaded():
            logger.info("Loading production knowledge base...")
            if not retriever.load("production"):
                logger.warning("Failed to load production KB, trying default...")
                retriever.load("default")

        # Retrieval knobs from config (single source of truth). The threshold
        # gates the semantic cosine pre-filter inside the hybrid retriever, so
        # it stays a real relevance floor even though results are re-ranked by
        # the keyword blend.
        try:
            from utils import get_config

            cfg = get_config()
            top_k = cfg.rag_top_k
            threshold = cfg.rag_threshold
        except Exception:
            top_k, threshold = 3, 0.4

        # Retrieve relevant documents
        results = retriever.retrieve(query, top_k=top_k, threshold=threshold)

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
            formatted_results.append(
                {
                    "title": metadata.get(
                        "section_title", metadata.get("filename", "Knowledge Base")
                    ),
                    "content": result["document"],
                    "score": round(result["score"], 2),
                    "category": metadata.get("category", "general"),
                    "source": metadata.get("filename", "unknown"),
                }
            )

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
            "results": [
                {
                    "title": "Router Troubleshooting",
                    "content": "Perkraukite routerį: išjunkite 30 sek, įjunkite atgal.",
                }
            ],
        }
    elif "wifi" in query_lower or "slaptažod" in query_lower:
        return {
            "success": True,
            "results": [
                {"title": "WiFi", "content": "WiFi slaptažodis yra ant routerio lipduko apačioje."}
            ],
        }

    return {
        "success": True,
        "results": [],
        "message": "No specific knowledge found (fallback mode).",
    }


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

        # The DB column `ticket_type` has a strict CHECK constraint; the model's free-text
        # `problem_type` (e.g. "equipment_replacement") would violate it and fail the INSERT
        # (database_error). Coerce to a valid type — anything not already valid becomes
        # `technician_visit` (every ticket here results in a worker contacting the customer)
        # — and keep the model's original wording in the details so nothing is lost.
        valid_ticket_types = {
            "network_issue",
            "resolved",
            "technician_visit",
            "customer_not_found",
            "no_service_area",
        }
        ticket_type = problem_type if problem_type in valid_ticket_types else "technician_visit"
        details = problem_description or ""
        if problem_type not in valid_ticket_types and problem_type:
            details = f"[{problem_type}] {details}".strip()

        args = {
            "customer_id": customer_id,
            "ticket_type": ticket_type,
            "priority": priority,
            "summary": (details[:100] if details else "Support request"),
            "details": details,
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
            # Normalize the inner CRM failure to our envelope instead of leaking
            # its raw shape to the agent.
            return {
                "success": False,
                "error": result.get("error", "ticket_creation_failed"),
                "message": result.get("message", "Failed to create ticket"),
            }

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
# CALL RECORD (Phase 3.10) — engine-internal, NOT an LLM-callable tool
# =============================================================================


def save_call_record(
    session_id: str,
    *,
    customer_id: str | None = None,
    messages: list | None = None,
    outcome: str | None = None,
    summary: dict | None = None,
    ticket_id: str | None = None,
    duration_seconds: int | None = None,
) -> dict:
    """Persist one call record to the conversations table (Phase 3.10 slice 1b).

    Called by the engine at session end, not by the model. Best-effort: a DB or
    import failure is swallowed to an error envelope so it can never break call
    teardown."""
    logger.info(f"[REC] save_call_record(session_id={session_id}, customer_id={customer_id})")
    try:
        db = get_db()

        from crm_mcp.tools.conversations import save_conversation

        return save_conversation(
            db,
            {
                "session_id": session_id,
                "customer_id": customer_id,
                "messages": messages or [],
                "outcome": outcome,
                "summary": summary,
                "ticket_id": ticket_id,
                "duration_seconds": duration_seconds,
            },
        )
    except Exception as e:  # pragma: no cover - defensive; never break teardown
        logger.error(f"Error saving call record: {e}", exc_info=True)
        return {"success": False, "error": "call_record_failed", "message": str(e)}


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
                summary = (
                    f"Aptiktos problemos. Paketų praradimas: {stats.get('packet_loss_percent', 0)}%"
                )
            else:
                summary = (
                    f"Kritinė problema. Paketų praradimas: {stats.get('packet_loss_percent', 0)}%"
                )

            return {
                "success": True,
                "customer_id": customer_id,
                "status": status,
                "statistics": stats,
                "summary": summary,
                "message": result.get("message"),
            }
        else:
            # Normalize the inner failure to our envelope instead of leaking
            # the raw ping_test result shape to the agent.
            return {
                "success": False,
                "error": result.get("error", "ping_test_error"),
                "message": result.get("message", "Ping test failed"),
            }

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


def close_case(reason: str = "resolved") -> dict:
    """
    Signal that the support case is finished and the call should move to closing.

    This is a SIGNAL tool: it does no DB work — the agent engine reads the result
    and flips the conversation into the tools-less closing stage (a polite
    goodbye). Reasons: "resolved" (service works again), "outage" (an active
    outage was reported and the caller is done asking about it), "declined" (the
    caller wants to end).

    Args:
        reason: Why the case closes — "resolved" | "outage" | "declined".

    Returns:
        Acknowledgement carrying the close signal (read by the engine).
    """
    logger.info(f"[TOOL] close_case(reason={reason})")
    reason = reason if reason in ("resolved", "outage", "declined") else "resolved"
    return {
        "success": True,
        "case_closed": True,
        "reason": reason,
        "message": "Byla uždaroma — pereinama prie atsisveikinimo.",
    }


# =============================================================================
# TOOLS REGISTRY
# =============================================================================

REAL_TOOLS = [
    Tool(
        name="resolve_address",
        description=(
            "PRIMARY identification tool. Resolve the customer's spoken service "
            "address — accepts PARTIAL input by design: call it as soon as you have "
            "city+street to verify early, then again with more parts. Returns a "
            "per-level diagnosis (city/street/house/apartment: ok / not_found / "
            "unclear / found_elsewhere alternatives / contracts_count) plus a 'hint' "
            "telling you exactly what to clarify next. On unique success returns the "
            "full customer profile."
        ),
        parameters={
            "city": {
                "type": "string",
                "description": (
                    "City or village as the customer said it. When BOTH a district "
                    "and a village are named ('Šiaulių rajonas, Bubių kaimas'), pass "
                    "the WHOLE phrase or at least the village — NEVER drop the "
                    "village and pass only 'Šiaulių rajonas'."
                ),
            },
            "street": {
                "type": "string",
                "description": "Street as heard (e.g. 'Dainų g', 'Girėno Dariaus')",
            },
            "house_number": {
                "type": "string",
                "description": "House number, may contain a letter (e.g. '12', '122F')",
            },
            "apartment_number": {
                "type": "string",
                "description": "Apartment number if the customer gave one",
            },
            "surname": {
                "type": "string",
                "description": "ONLY for confirmation/disambiguation when the tool asks — the customer says it first",
            },
        },
        function=resolve_address,
    ),
    Tool(
        name="find_customer",
        description=(
            "Helper lookups: by the caller's phone (mandatory fallback when "
            "resolve_address fails) or by account code (abonento kodas — fastest "
            "path when the customer knows it). For addresses use resolve_address."
        ),
        parameters={
            "phone": {
                "type": "string",
                "description": "Phone number (e.g., +37061234567 or 861234567)",
            },
            "account_code": {
                "type": "string",
                "description": "Invoice account code (abonento kodas), e.g. 'AB-10101'",
            },
            "address": {
                "type": "string",
                "description": "Legacy single-string address (prefer resolve_address)",
            },
            "name": {"type": "string", "description": "Customer name (not supported)"},
        },
        function=find_customer,
    ),
    Tool(
        name="diagnose_connection",
        description=(
            "PRIMARY diagnostic for 'no internet' complaints. One call checks "
            "billing, registered outages, switch, port and equipment signals and "
            "returns a deterministic verdict: side (provider/customer/unclear), "
            "group, action (inform/create_ticket/instruct) and agent_message with "
            "guidance. Call it right after the customer is identified. Follow the "
            "verdict's action; when side is customer/unclear, continue the "
            "conversation to pin down the cause."
        ),
        parameters={
            "customer_id": {
                "type": "string",
                "description": "Customer ID from CRM",
                "required": True,
            },
        },
        function=diagnose_connection,
    ),
    Tool(
        name="check_network_status",
        description="Check network status for a customer - port status, IP assignment, signal quality. Use this to diagnose connection issues.",
        parameters={
            "customer_id": {
                "type": "string",
                "description": "Customer ID from CRM",
                "required": True,
            },
            "address_id": {
                "type": "string",
                "description": "Specific address ID if customer has multiple",
            },
        },
        function=check_network_status,
    ),
    Tool(
        name="check_outages",
        description="Check for active outages or planned works. Can check by area name or customer ID.",
        parameters={
            "area": {
                "type": "string",
                "description": "Area/city to check (e.g., 'Šiauliai', 'Kaunas')",
            },
            "customer_id": {
                "type": "string",
                "description": "Customer ID to check if affected by outages",
            },
        },
        function=check_outages,
    ),
    Tool(
        name="run_ping_test",
        description="Run ping/latency test for customer connection. Shows packet loss and response times.",
        parameters={
            "customer_id": {
                "type": "string",
                "description": "Customer ID from CRM",
                "required": True,
            },
        },
        function=run_ping_test,
    ),
    Tool(
        name="update_mac",
        description=(
            "SIMULATED remote action: bind the device currently seen on the "
            "customer's line (re-binds port authorization to the observed MAC, "
            "refreshes the lease, updates the equipment registry). Use ONLY after "
            "the customer confirms they connected a different device: replaced "
            "router (B6 foreign MAC) or the bridge-until-technician options "
            "(cable straight into a PC / customer's own router). Follow with "
            "reset_port."
        ),
        parameters={
            "customer_id": {
                "type": "string",
                "description": "Customer ID from CRM",
                "required": True,
            },
        },
        function=update_mac,
    ),
    Tool(
        name="reset_port",
        description=(
            "SIMULATED remote action: bounce the customer's switch port/session "
            "(forces re-authorization). Use right after update_mac, or for a "
            "suspected session freeze."
        ),
        parameters={
            "customer_id": {
                "type": "string",
                "description": "Customer ID from CRM",
                "required": True,
            },
        },
        function=reset_port,
    ),
    Tool(
        name="search_knowledge",
        description="Search troubleshooting knowledge base for solutions. Use for router issues, WiFi problems, TV issues etc.",
        parameters={
            "query": {
                "type": "string",
                "description": "Search query describing the problem",
                "required": True,
            },
        },
        function=search_knowledge,
    ),
    Tool(
        name="create_ticket",
        description="Create support ticket for technician visit or escalation. Only use when problem cannot be resolved remotely.",
        parameters={
            "customer_id": {"type": "string", "description": "Customer ID", "required": True},
            "problem_type": {
                "type": "string",
                "description": "Type: network_issue, technician_visit, equipment_replacement",
            },
            "problem_description": {
                "type": "string",
                "description": "Detailed problem description",
            },
            "priority": {"type": "string", "description": "Priority: low, medium, high, critical"},
            "notes": {"type": "string", "description": "Additional notes for technician"},
        },
        function=create_ticket,
    ),
    Tool(
        name="close_case",
        description=(
            "Finish the support case and move to a polite goodbye. Call this ONLY "
            "when the customer confirms the service is ALREADY WORKING NOW (present "
            "tense), or has acknowledged a reported outage and is done, or clearly "
            "wants to end the call. Do NOT call it when the customer merely hopes or "
            "expects it will work after a step — wait until they confirm it works."
        ),
        parameters={
            "reason": {
                "type": "string",
                "description": "resolved (works again) | outage (outage reported, caller done) | declined (caller ends)",
            },
        },
        function=close_case,
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


def get_tools_schema() -> list[dict]:
    """
    Export all registered tools as OpenAI function-calling schemas.

    This is what gets passed as `tools=...` to the LLM. Native function
    calling replaces the old prose `get_tools_description()` prompt: instead
    of describing tools in text and parsing a ReAct "Action:" block back out,
    the model receives structured schemas and returns structured tool calls.
    """
    return [tool.to_openai_schema() for tool in REAL_TOOLS]


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments (validated against its schema)."""
    for tool in REAL_TOOLS:
        if tool.name == tool_name:
            # Guard at the boundary: never call the function with unvalidated,
            # model-supplied arguments. A validation error is returned as the
            # observation so the model can self-correct instead of crashing.
            cleaned_args, error = tool.validate_arguments(arguments)
            if error is not None:
                logger.warning(f"[TOOL] {tool_name} argument validation failed: {error}")
                return json.dumps(error, ensure_ascii=False)

            try:
                result = tool.function(**cleaned_args)
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

    # Mask phone numbers in logs (after basicConfig set up the root handler).
    from utils import install_pii_redaction

    install_pii_redaction()

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
