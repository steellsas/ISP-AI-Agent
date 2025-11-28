"""
Ticket Registration Node
Create support ticket via CRM MCP service when problem cannot be resolved
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message, add_tool_call, get_last_user_message

logger = get_logger(__name__)


def ticket_registration_node(state: ConversationState) -> ConversationState:
    """
    Ticket registration node - Create support ticket.
    
    This node:
    1. Gathers all relevant information from state
    2. Creates ticket via CRM MCP service
    3. Provides ticket confirmation to customer
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with ticket information
    """
    logger.info(f"[TicketReg] Creating ticket for conversation {state['conversation_id']}")
    
    try:
        language = state["language"]
        
        # Check if we have customer info
        customer_id = state["customer"].get("customer_id")
        
        if not customer_id:
            logger.warning("[TicketReg] No customer ID, creating anonymous ticket")
            state = _create_anonymous_ticket_notification(state, language)
            return state
        
        # Gather ticket information
        ticket_data = _prepare_ticket_data(state)
        
        # Inform customer ticket is being created
        state = add_message(
            state,
            "assistant",
            _get_creating_ticket_message(language)
        )
        
        # TODO: Call CRM MCP service to create ticket
        # This will be replaced with actual MCP client call:
        # from ...mcp_client import call_crm_tool
        # ticket_result = await call_crm_tool("create_ticket", ticket_data)
        
        ticket_result = _simulate_ticket_creation(ticket_data)
        
        # Log tool call
        state = add_tool_call(state, "create_ticket", ticket_data, ticket_result)
        
        if ticket_result.get("success"):
            # Ticket created successfully
            ticket_info = ticket_result["ticket"]
            state["ticket"]["ticket_id"] = ticket_info["ticket_id"]
            state["ticket"]["ticket_type"] = ticket_info["ticket_type"]
            state["ticket"]["priority"] = ticket_info["priority"]
            state["ticket"]["summary"] = ticket_info["summary"]
            state["ticket"]["created"] = True
            state["ticket_created"] = True
            
            # Confirm ticket creation to customer
            confirmation = _create_ticket_confirmation(ticket_info, language)
            state = add_message(state, "assistant", confirmation)
            
            logger.info(f"[TicketReg] Ticket created: {ticket_info['ticket_id']}")
            
        else:
            # Ticket creation failed
            state = _handle_ticket_creation_failure(state, ticket_result, language)
            logger.error(f"[TicketReg] Ticket creation failed: {ticket_result.get('message')}")
        
        state["current_node"] = "ticket_registration"
        return state
        
    except Exception as e:
        logger.error(f"[TicketReg] Error: {e}", exc_info=True)
        state = _handle_ticket_error(state)
        return state


def _prepare_ticket_data(state: ConversationState) -> Dict[str, Any]:
    """
    Prepare ticket data from conversation state.
    
    Args:
        state: Current conversation state
        
    Returns:
        Ticket data dictionary
    """
    customer = state["customer"]
    problem = state["problem"]
    troubleshooting = state["troubleshooting"]
    diagnostics = state["diagnostics"]
    
    # Determine ticket type
    ticket_type = _determine_ticket_type(problem, diagnostics)
    
    # Determine priority
    priority = _determine_ticket_priority(problem, diagnostics)
    
    # Create summary
    summary = _create_ticket_summary(problem, state["language"])
    
    # Create detailed description
    details = _create_ticket_details(state)
    
    # Compile troubleshooting steps taken
    troubleshooting_steps = "\n".join([
        f"- {step}" for step in troubleshooting.get("instructions_given", [])
    ])
    
    ticket_data = {
        "customer_id": customer.get("customer_id"),
        "ticket_type": ticket_type,
        "priority": priority,
        "summary": summary,
        "details": details,
        "troubleshooting_steps": troubleshooting_steps if troubleshooting_steps else "No troubleshooting attempted"
    }
    
    return ticket_data


def _determine_ticket_type(
    problem: Dict[str, Any],
    diagnostics: Dict[str, Any]
) -> str:
    """Determine ticket type based on problem and diagnostics."""
    
    category = problem.get("category")
    analysis = diagnostics.get("analysis", {})
    
    # Check if requires technician visit
    if analysis.get("requires_escalation"):
        return "technician_visit"
    
    # Map problem categories to ticket types
    if category in ["internet_no_connection", "tv_no_signal"]:
        return "network_issue"
    elif category in ["internet_slow", "internet_intermittent"]:
        return "network_issue"
    else:
        return "network_issue"


def _determine_ticket_priority(
    problem: Dict[str, Any],
    diagnostics: Dict[str, Any]
) -> str:
    """Determine ticket priority."""
    
    category = problem.get("category")
    analysis = diagnostics.get("analysis", {})
    
    # Critical if complete service failure
    if category in ["internet_no_connection", "tv_no_signal"]:
        return "high"
    
    # High if diagnostics show critical issues
    if analysis.get("requires_escalation"):
        return "high"
    
    # Medium for performance issues
    if category in ["internet_slow", "tv_poor_quality"]:
        return "medium"
    
    # Default to medium
    return "medium"


def _create_ticket_summary(problem: Dict[str, Any], language: str) -> str:
    """Create brief ticket summary."""
    
    category = problem.get("category", "unknown")
    
    summaries = {
        "lt": {
            "internet_no_connection": "Internetas neveikia",
            "internet_slow": "Lėtas interneto greitis",
            "internet_intermittent": "Internetas nutrūkinėja",
            "tv_no_signal": "Televizija neveikia - nėra signalo",
            "tv_poor_quality": "Prastos kokybės TV vaizdas",
            "unknown": "Techninis gedimas"
        },
        "en": {
            "internet_no_connection": "Internet not working",
            "internet_slow": "Slow internet speed",
            "internet_intermittent": "Internet keeps disconnecting",
            "tv_no_signal": "TV not working - no signal",
            "tv_poor_quality": "Poor quality TV picture",
            "unknown": "Technical issue"
        }
    }
    
    return summaries.get(language, summaries["lt"]).get(category, summaries[language]["unknown"])


def _create_ticket_details(state: ConversationState) -> str:
    """Create detailed ticket description."""
    
    details = []
    
    # Problem description
    problem_desc = state["problem"].get("description", "")
    if problem_desc:
        details.append(f"CUSTOMER REPORT:\n{problem_desc}")
    
    # Diagnostic results summary
    diagnostics = state["diagnostics"]
    if diagnostics.get("analysis"):
        analysis = diagnostics["analysis"]
        if analysis.get("issues"):
            details.append(f"\nDIAGNOSTIC ISSUES:\n" + "\n".join(f"- {issue}" for issue in analysis["issues"]))
        if analysis.get("healthy_components"):
            details.append(f"\nHEALTHY COMPONENTS:\n" + "\n".join(f"- {comp}" for comp in analysis["healthy_components"]))
    
    # Customer info
    customer = state["customer"]
    if customer.get("phone"):
        details.append(f"\nCUSTOMER CONTACT: {customer['phone']}")
    
    return "\n".join(details)


def _simulate_ticket_creation(ticket_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulate ticket creation (temporary until MCP client is integrated).
    
    Args:
        ticket_data: Ticket information
        
    Returns:
        Simulated ticket result
    """
    import uuid
    from datetime import datetime
    
    ticket_id = f"TKT{uuid.uuid4().hex[:8].upper()}"
    
    return {
        "success": True,
        "ticket": {
            "ticket_id": ticket_id,
            "customer_id": ticket_data.get("customer_id"),
            "ticket_type": ticket_data.get("ticket_type"),
            "priority": ticket_data.get("priority"),
            "summary": ticket_data.get("summary"),
            "created_at": datetime.now().isoformat()
        },
        "message": f"Gedimo pranešimas {ticket_id} sėkmingai sukurtas"
    }


def _create_ticket_confirmation(ticket_info: Dict[str, Any], language: str) -> str:
    """Create ticket confirmation message."""
    
    ticket_id = ticket_info["ticket_id"]
    priority = ticket_info["priority"]
    
    priority_translations = {
        "lt": {"high": "Aukštas", "medium": "Vidutinis", "low": "Žemas"},
        "en": {"high": "High", "medium": "Medium", "low": "Low"}
    }
    
    priority_text = priority_translations.get(language, priority_translations["lt"]).get(priority, priority)
    
    if language == "lt":
        message = f"""✅ **Gedimo pranešimas sukurtas!**

**Numeris:** {ticket_id}
**Prioritetas:** {priority_text}

Mūsų technikas susisieks su Jumis per:
• Aukšto prioriteto - 4 valandas
• Vidutinio prioriteto - 24 valandas

Galite nurodyti šį numerį susisiekdami su mumis.

Ar dar kažkas, kuo galėčiau padėti?"""
    else:
        message = f"""✅ **Support ticket created!**

**Number:** {ticket_id}
**Priority:** {priority_text}

Our technician will contact you within:
• High priority - 4 hours
• Medium priority - 24 hours

You can reference this number when contacting us.

Is there anything else I can help you with?"""
    
    return message


def _create_anonymous_ticket_notification(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Create notification for anonymous ticket creation."""
    
    if language == "lt":
        message = """Kadangi neturiu Jūsų kliento duomenų, negaliu sukurti gedimo pranešimo sistemoje.

Prašau susisiekti su mumis tiesiogiai:
📞 **Telefonu:** +370 000 0000
✉️ **El. paštu:** pagalba@isp.lt

Dirbame: Pr-Pt 8:00-20:00, Št 9:00-17:00"""
    else:
        message = """Since I don't have your customer information, I cannot create a support ticket in the system.

Please contact us directly:
📞 **Phone:** +370 000 0000
✉️ **Email:** support@isp.lt

Working hours: Mon-Fri 8:00-20:00, Sat 9:00-17:00"""
    
    state = add_message(state, "assistant", message)
    state["ticket"]["created"] = False
    state["ticket_created"] = False
    
    return state


def _handle_ticket_creation_failure(
    state: ConversationState,
    result: Dict[str, Any],
    language: str
) -> ConversationState:
    """Handle ticket creation failure."""
    
    error_message = result.get("message", "Unknown error")
    
    if language == "lt":
        message = f"""Atsiprašau, nepavyko sukurti gedimo pranešimo dėl techninės klaidos.

Prašau susisiekti su mumis tiesiogiai:
📞 +370 000 0000

Klaidos pranešimas: {error_message}"""
    else:
        message = f"""Sorry, couldn't create support ticket due to a technical error.

Please contact us directly:
📞 +370 000 0000

Error message: {error_message}"""
    
    state = add_message(state, "assistant", message)
    state["ticket_created"] = False
    
    return state


def _get_creating_ticket_message(language: str) -> str:
    """Get 'creating ticket' message."""
    if language == "lt":
        return "🎫 Kuriu gedimo pranešimą..."
    else:
        return "🎫 Creating support ticket..."


def _handle_ticket_error(state: ConversationState) -> ConversationState:
    """Handle unexpected ticket creation errors."""
    language = state["language"]
    
    if language == "lt":
        message = """Atsiprašau, įvyko nenumatyta klaida kuriant pranešimą.

Prašau susisiekti su mumis telefonu: +370 000 0000"""
    else:
        message = """Sorry, an unexpected error occurred creating the ticket.

Please contact us by phone: +370 000 0000"""
    
    state = add_message(state, "assistant", message)
    state["ticket_created"] = False
    
    return state
