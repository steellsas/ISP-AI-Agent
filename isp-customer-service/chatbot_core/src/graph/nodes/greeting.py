"""
Greeting Node
Welcome the customer and set up the conversation
"""

import sys
from pathlib import Path

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message

logger = get_logger(__name__)


# Greeting messages by language
GREETINGS = {
    "lt": """Sveiki! 👋

Aš esu ISP pagalbos asistentas. Padėsiu išspręsti Jūsų interneto ar televizijos problemas 22.

Norėdamas pradėti, man reikės kelių dalykų:
• Jūsų adreso (miestas, gatvė, namo numeris)
• Trumpo problemos aprašymo

Kaip galiu Jums padėti šiandien?""",
    
    "en": """Hello! 👋

I'm the ISP support assistant. I'll help you resolve your internet or TV issues.

To get started, I'll need:
• Your address (city, street, house number)
• A brief description of the problem

How can I help you today?"""
}


def greeting_node(state: ConversationState) -> ConversationState:
    """
    Greeting node - Welcome customer and explain what information is needed.
    
    This is the entry point of the workflow. It:
    1. Greets the customer in their language
    2. Explains what information is needed
    3. Sets up the initial conversation state
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with greeting message
    """
    logger.info(f"[Greeting] Starting conversation {state['conversation_id']}")
    
    try:
        # Get greeting message in appropriate language
        language = state.get("language", "lt")
        greeting_message = GREETINGS.get(language, GREETINGS["lt"])
        
        # Add greeting to conversation
        state = add_message(state, "assistant", greeting_message)
        
        # Update current node
        # state["current_node"] = "greeting"
        state["current_node"] = "customer_identification"
        
        # Log metadata
        state["metadata"]["greeting_sent"] = True
        state["metadata"]["greeting_timestamp"] = state["session_start"]
        
        logger.info(f"[Greeting] Greeting sent in {language}")
        
        return state
        
    except Exception as e:
        logger.error(f"[Greeting] Error: {e}", exc_info=True)
        
        # Fallback greeting in case of error
        fallback_message = "Sveiki! Kaip galiu Jums padėti?"
        state = add_message(state, "assistant", fallback_message)
        state["current_node"] = "greeting"
        
        return state


def create_personalized_greeting(
    state: ConversationState,
    customer_name: str = None
) -> str:
    """
    Create personalized greeting if customer is returning.
    
    Args:
        state: Current conversation state
        customer_name: Customer's first name (optional)
        
    Returns:
        Personalized greeting message
    """
    language = state.get("language", "lt")
    
    if customer_name:
        if language == "lt":
            return f"""Sveiki, {customer_name}! 👋

Smagu Jus vėl matyti. Kaip galiu padėti šiandien?"""
        else:
            return f"""Hello, {customer_name}! 👋

Good to see you again. How can I help you today?"""
    else:
        return GREETINGS.get(language, GREETINGS["lt"])


def get_greeting_with_context(
    state: ConversationState,
    time_of_day: str = None
) -> str:
    """
    Get greeting with time-of-day context.
    
    Args:
        state: Current conversation state
        time_of_day: "morning", "afternoon", "evening" (optional)
        
    Returns:
        Contextual greeting
    """
    language = state.get("language", "lt")
    
    # Time-based greetings
    time_greetings = {
        "lt": {
            "morning": "Labas rytas! ☀️",
            "afternoon": "Laba diena! 👋",
            "evening": "Labas vakaras! 🌙"
        },
        "en": {
            "morning": "Good morning! ☀️",
            "afternoon": "Good afternoon! 👋",
            "evening": "Good evening! 🌙"
        }
    }
    
    if time_of_day and time_of_day in time_greetings.get(language, {}):
        greeting_start = time_greetings[language][time_of_day]
    else:
        greeting_start = "Sveiki! 👋" if language == "lt" else "Hello! 👋"
    
    if language == "lt":
        return f"""{greeting_start}

Aš esu ISP pagalbos asistentas. Padėsiu išspręsti Jūsų interneto ar televizijos problemas.

Kaip galiu Jums padėti?"""
    else:
        return f"""{greeting_start}

I'm the ISP support assistant. I'll help you resolve your internet or TV issues.

How can I help you today?"""