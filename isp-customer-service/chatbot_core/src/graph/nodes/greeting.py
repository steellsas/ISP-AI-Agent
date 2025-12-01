
"""
Greeting Node - First contact with customer

Returns static greeting from config. No LLM call needed.
"""

from src.config.config import load_config, get_greeting
from src.graph.state import add_message


def greeting_node(state) -> dict:
    """
    Greeting node - pasisveikina su klientu.
    
    Tai pirmas node workflow'e. Grąžina statinį tekstą iš config.
    Jokio LLM call - minimali latency.
    
    Args:
        state: Current conversation state (Pydantic object)
        
    Returns:
        State update with greeting message
    """
    # Load config and get greeting
    config = load_config()
    greeting_text = get_greeting(config)
    
    # Create message
    message = add_message(
        role="assistant",
        content=greeting_text,
        node="greeting"
    )
    
    return {
        "messages": [message],
        "current_node": "greeting"
    }