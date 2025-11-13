"""
Resolution Node
End conversation and provide final summary
"""

import sys
from pathlib import Path
from typing import Dict, Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message

logger = get_logger(__name__)


def resolution_node(state: ConversationState) -> ConversationState:
    """
    Resolution node - End conversation gracefully.
    
    This node:
    1. Provides conversation summary
    2. Thanks the customer
    3. Offers additional help if needed
    4. Marks conversation as ended
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with conversation ended
    """
    logger.info(f"[Resolution] Ending conversation {state['conversation_id']}")
    
    try:
        language = state["language"]
        
        # Create resolution message based on outcome
        resolution_message = _create_resolution_message(state, language)
        state = add_message(state, "assistant", resolution_message)
        
        # Mark conversation as ended
        state["conversation_ended"] = True
        state["current_node"] = "resolution"
        
        # Log outcome
        outcome = _determine_outcome(state)
        logger.info(f"[Resolution] Conversation ended with outcome: {outcome}")
        state["metadata"]["outcome"] = outcome
        
        return state
        
    except Exception as e:
        logger.error(f"[Resolution] Error: {e}", exc_info=True)
        state = _handle_resolution_error(state)
        return state


def _create_resolution_message(state: ConversationState, language: str) -> str:
    """
    Create appropriate resolution message based on conversation outcome.
    
    Args:
        state: Current conversation state
        language: Language
        
    Returns:
        Resolution message
    """
    # Determine outcome
    if state["troubleshooting"].get("resolved"):
        return _create_resolved_message(state, language)
    elif state["ticket_created"]:
        return _create_ticket_created_message(state, language)
    else:
        return _create_generic_ending_message(state, language)


def _create_resolved_message(state: ConversationState, language: str) -> str:
    """Create message when problem was resolved."""
    
    customer_name = state["customer"].get("first_name", "")
    
    if language == "lt":
        greeting = f"Puiku, {customer_name}!" if customer_name else "Puiku!"
        return f"""{greeting} 🎉

Džiaugiuosi, kad pavyko išspręsti problemą!

**Ką padarėme:**
• Identifikavome problemą
• Atlikome diagnostiką
• Išsprendėme troubleshooting žingsniais

Jei problema vėl pasikartos, žinokite kad galite bet kada kreiptis.

**Kontaktai:**
📞 +370 000 0000
✉️ pagalba@isp.lt

Ačiū, kad pasirinkote mūsų paslaugas! Geros dienos! 😊"""
    else:
        greeting = f"Great, {customer_name}!" if customer_name else "Great!"
        return f"""{greeting} 🎉

I'm glad we were able to resolve the problem!

**What we did:**
• Identified the problem
• Ran diagnostics
• Resolved through troubleshooting steps

If the problem recurs, know that you can contact us anytime.

**Contact:**
📞 +370 000 0000
✉️ support@isp.lt

Thank you for choosing our services! Have a great day! 😊"""


def _create_ticket_created_message(state: ConversationState, language: str) -> str:
    """Create message when ticket was created."""
    
    ticket_id = state["ticket"].get("ticket_id", "")
    priority = state["ticket"].get("priority", "medium")
    
    # Response time based on priority
    response_times = {
        "high": ("4 valandas", "4 hours"),
        "medium": ("24 valandas", "24 hours"),
        "low": ("48 valandas", "48 hours")
    }
    
    response_time = response_times.get(priority, response_times["medium"])
    time_text = response_time[0] if language == "lt" else response_time[1]
    
    if language == "lt":
        return f"""**Veiksmai atlikti:** ✅

• Atlikta diagnostika
• Išbandyti troubleshooting žingsniai
• Sukurtas gedimo pranešimas **{ticket_id}**

**Kas toliau?**
Mūsų technikas susisieks su Jumis per **{time_text}**.

Jei reikės skubios pagalbos, skambinkite: 📞 +370 000 0000

Nurodykit pranešimo numerį: **{ticket_id}**

Ačiū už kantrybę ir pasitikėjimą! 😊"""
    else:
        return f"""**Actions taken:** ✅

• Diagnostics completed
• Troubleshooting steps attempted
• Support ticket created **{ticket_id}**

**What's next?**
Our technician will contact you within **{time_text}**.

If you need urgent help, call: 📞 +370 000 0000

Reference ticket number: **{ticket_id}**

Thank you for your patience and trust! 😊"""


def _create_generic_ending_message(state: ConversationState, language: str) -> str:
    """Create generic ending message."""
    
    if language == "lt":
        return """Ačiū, kad kreipėtės!

Jei reikės daugiau pagalbos, visada galite:
📞 Skambinti: +370 000 0000
✉️ Rašyti: pagalba@isp.lt
💬 Grįžti čia ir parašyti man

Dirbame: Pr-Pt 8:00-20:00, Št 9:00-17:00

Geros dienos! 😊"""
    else:
        return """Thank you for contacting us!

If you need more help, you can always:
📞 Call: +370 000 0000
✉️ Email: support@isp.lt
💬 Come back here and message me

Working hours: Mon-Fri 8:00-20:00, Sat 9:00-17:00

Have a great day! 😊"""


def _determine_outcome(state: ConversationState) -> str:
    """Determine conversation outcome for logging."""
    
    if state["troubleshooting"].get("resolved"):
        return "resolved"
    elif state["ticket_created"]:
        return "ticket_created"
    elif not state["customer_identified"]:
        return "customer_not_identified"
    elif not state["problem_identified"]:
        return "problem_not_identified"
    else:
        return "incomplete"


def _handle_resolution_error(state: ConversationState) -> ConversationState:
    """Handle resolution errors."""
    language = state["language"]
    
    if language == "lt":
        message = """Ačiū, kad kreipėtės!

Jei reikia pagalbos, skambinkite: 📞 +370 000 0000

Geros dienos! 😊"""
    else:
        message = """Thank you for contacting us!

If you need help, call: 📞 +370 000 0000

Have a great day! 😊"""
    
    state = add_message(state, "assistant", message)
    state["conversation_ended"] = True
    
    return state
