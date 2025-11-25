"""
Closing Node
Ends the conversation gracefully
"""

from typing import Dict, Any
from ..state import ConversationState, add_message, get_last_user_message
from ...services.llm_service import get_llm_service
from ...config.old.prompts import CLOSING_PROMPT, GOODBYE_PROMPT


async def closing_node_async(state: ConversationState) -> Dict[str, Any]:
    """
    Close the conversation.
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state
    """
    
    # Check if already asked
    if state.get("last_question") == "anything_else":
        user_response = get_last_user_message(state)
        
        if user_response:
            # Use LLM to understand intent (singleton getter)
            llm = get_llm_service()
            intent = await llm.classify_intent(
                user_message=user_response,
                intents=["yes_more_help", "no_thanks", "unclear"]
            )
            
            if intent == "yes_more_help":
                # Loop back - user has another problem
                state["conversation_ended"] = False
                state["next_action"] = "restart"
                state["waiting_for_user_input"] = False
                
                # Reset some state for new issue
                state["problem_identified"] = False
                state["problem"] = {}
                
                return {
                    "conversation_ended": False,
                    "next_action": "restart",
                    "waiting_for_user_input": False,
                    "problem_identified": False,
                    "problem": {},
                    "current_node": "closing"
                }
            else:
                # Really ending (no_thanks or unclear treated as ending)
                goodbye = await llm.generate(
                    system_prompt=GOODBYE_PROMPT,
                    messages=[],
                    temperature=0.7,
                    max_tokens=100
                )
                
                state = add_message(
                    state=state,
                    role="assistant",
                    content=goodbye,
                    node="closing"
                )
                
                state["conversation_ended"] = True
                state["current_node"] = "closing"
                state["waiting_for_user_input"] = False
                
                return {
                    "messages": state["messages"],
                    "conversation_ended": True,
                    "current_node": state["current_node"],
                    "waiting_for_user_input": False
                }
    
    # First time - ask if anything else
    question = "Ar dar kuo galiu padėti?"
    
    state = add_message(
        state=state,
        role="assistant",
        content=question,
        node="closing"
    )
    
    state["waiting_for_user_input"] = True
    state["last_question"] = "anything_else"
    state["current_node"] = "closing"
    
    return {
        "messages": state["messages"],
        "waiting_for_user_input": True,
        "last_question": "anything_else",
        "current_node": state["current_node"]
    }


# def run(state: ConversationState) -> Dict[str, Any]:
#     """Synchronous wrapper for LangGraph with nested loop support."""
#     import asyncio
#     import nest_asyncio
    
#     nest_asyncio.apply()
    
#     try:
#         loop = asyncio.get_event_loop()
#     except RuntimeError:
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
    
#     return loop.run_until_complete(closing_node_async(state))