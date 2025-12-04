"""
Greeting Node - First contact with customer

Returns static greeting from translations. No LLM call needed.
Supports multiple languages via translation service.
"""

import logging
from typing import Any

from src.config.config import load_config
from src.graph.state import add_message, _get_attr
from src.services.language_service import (
    sync_language_from_state, 
    get_agent_name, 
    get_language
)
from src.services.translation_service import t

logger = logging.getLogger(__name__)


# =============================================================================
# NODE FUNCTION
# =============================================================================

def greeting_node(state: Any) -> dict:
    """
    Greeting node - greets the customer.
    
    This is the first node in the workflow. Returns static text from
    translation files. No LLM call - minimal latency.
    
    Supports:
    - Multiple languages (LT/EN) via translation service
    - Personalized greeting for returning customers
    - Structured logging
    - Error handling with fallback
    
    Args:
        state: Current conversation state (Pydantic object or dict)
        
    Returns:
        State update with greeting message
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    

    lang = sync_language_from_state(state)
    
    logger.info(f"[{conversation_id}] Greeting node started | language={lang}")
    
    try:
        # Load config for company name
        config = load_config()
        company_name = config.agent.company_name
        
        # Get agent name based on current language (now synced from state)
        agent_name = get_agent_name()
        
        # Check if returning customer (has customer_name in state)
        customer_name = _get_attr(state, "customer_name")
        
        if customer_name:
            # Returning customer - personalized greeting
            greeting_text = t(
                "greeting.welcome_returning",
                customer_name=customer_name
            )
            logger.info(f"[{conversation_id}] Returning customer: {customer_name}")
        else:
            # New customer - standard greeting
            greeting_text = t(
                "greeting.welcome",
                company_name=company_name,
                agent_name=agent_name
            )
            logger.info(f"[{conversation_id}] New customer greeting")
        
        # Create message
        message = add_message(
            role="assistant",
            content=greeting_text,
            node="greeting"
        )
        
        logger.info(f"[{conversation_id}] Greeting node completed | lang={lang} | agent={agent_name}")
        
        return {
            "messages": [message],
            "current_node": "greeting"
        }
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Greeting node error: {e}", exc_info=True)
        
        # Fallback greeting - language-aware
        current_lang = get_language()
        if current_lang == "en":
            fallback_greeting = "Hello! How can I help you today?"
        else:
            fallback_greeting = "Labas! Kuo galiu jums padėti?"
        
        message = add_message(
            role="assistant",
            content=fallback_greeting,
            node="greeting"
        )
        
        return {
            "messages": [message],
            "current_node": "greeting",
            "last_error": str(e)
        }


# =============================================================================
# ALTERNATIVE: Async version (if needed in future)
# =============================================================================

async def greeting_node_async(state: Any) -> dict:
    """
    Async version of greeting node.
    
    Currently just wraps sync version, but allows for future
    async operations if needed (e.g., async config loading).
    """
    return greeting_node(state)
