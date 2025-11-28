# """
# Greeting Node
# First interaction - welcomes the customer (no wait)
# """

# from typing import Dict, Any
# from ..state import ConversationState, add_message
# from ...services.llm_service import get_llm_service
# from ...config.old.prompts import GREETING_PROMPT, format_prompt


# async def greeting_node_async(state: ConversationState) -> Dict[str, Any]:
#     """
#     Welcome the customer and initiate conversation.
    
#     This node generates greeting and immediately proceeds to next node.
#     Does NOT wait for user input.
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         Updated state with greeting message
#     """
    
#     # Initialize LLM service (use singleton getter)
#     llm = get_llm_service()
    
#     # Prepare system prompt
#     system_prompt = format_prompt(
#         GREETING_PROMPT,
#         language=state["language"]
#     )
    
#     # Generate greeting
#     greeting_message = await llm.generate(
#         system_prompt=system_prompt,
#         messages=[],  # Empty for greeting
#         temperature=0.7,
#         max_tokens=150
#     )
    
#     # Update state
#     state = add_message(
#         state=state,
#         role="assistant",
#         content=greeting_message,
#         node="greeting"
#     )
    
#     # Set current node but DO NOT WAIT
#     state["current_node"] = "greeting"
#     state["waiting_for_user_input"] = False  # ← CHANGED: Ne-pause
    
#     return {
#         "messages": state["messages"],
#         "current_node": state["current_node"],
#         "waiting_for_user_input": False  # ← CRITICAL: Proceed immediately
#     }


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