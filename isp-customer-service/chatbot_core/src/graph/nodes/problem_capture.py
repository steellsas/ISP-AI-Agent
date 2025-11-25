"""
Problem Capture Node - Extracts and clarifies customer problem

Uses LLM to:
1. Analyze customer's message
2. Determine if problem is clear enough
3. Ask clarification questions if needed
4. Extract problem_type and description when clear
"""

import sys
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import Literal

# Try to import from shared module
try:
    shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
    if str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from utils import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

from src.services.llm import llm_json_completion
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = get_logger(__name__)


# === Structured Output Schema ===

class ProblemAnalysis(BaseModel):
    """LLM response schema for problem analysis."""
    problem_type: Literal["internet", "tv", "phone", "other"] | None = None
    problem_description: str | None = None
    is_clear: bool = False
    clarification_question: str | None = None
    confidence: float = 0.0  # 0-1, how confident about understanding


# === Prompts ===

SYSTEM_PROMPT = """Tu esi ISP (interneto tiekėjo) klientų aptarnavimo asistentas.
Tavo užduotis - suprasti kliento problemą.

Analizuok kliento žinutę ir nuspręsk:
1. Ar problema aiški? (is_clear)
2. Kokio tipo problema? (internet/tv/phone/other)
3. Trumpas problemos aprašymas
4. Jei neaišku - koks klausimas padėtų patikslinti?

Atsakyk JSON formatu:
{
    "problem_type": "internet" | "tv" | "phone" | "other" | null,
    "problem_description": "trumpas aprašymas arba null",
    "is_clear": true | false,
    "clarification_question": "klausimas lietuviškai arba null",
    "confidence": 0.0-1.0
}

Problema aiški (is_clear=true) kai:
- Žinai problemos tipą (internet/tv/phone)
- Supranti kas konkrečiai neveikia
- Confidence >= 0.7

Jei klientas tik pasisveikino arba neaišku - klausk patikslinti.
Būk draugiškas, klausimai turi būti natūralūs lietuviškai."""


def build_messages_for_llm(state) -> list[dict]:
    """Build message list for LLM from conversation state."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history (last N messages)
    state_messages = _get_messages(state)
    for msg in state_messages[-10:]:
        if msg["role"] in ("user", "assistant"):
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    return messages


def problem_capture_node(state) -> dict:
    """
    Problem capture node - analyzes and clarifies customer problem.
    
    Flow:
    1. Get user message
    2. Send to LLM for analysis
    3. If clear → update state with problem info
    4. If not clear → respond with clarification question
    
    Args:
        state: Current conversation state (Pydantic object)
        
    Returns:
        State update dict
    """
    logger.info("=== Problem Capture Node ===")
    
    user_message = get_last_user_message(state)
    logger.info(f"User message: {user_message}")
    
    if not user_message:
        # No user message yet - shouldn't happen, but handle gracefully
        logger.warning("No user message found")
        return {
            "current_node": "problem_capture"
        }
    
    # Build messages and call LLM
    messages = build_messages_for_llm(state)
    
    try:
        response = llm_json_completion(
            messages=messages,
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=300
        )
        
        analysis = ProblemAnalysis(**response)
        logger.info(f"Analysis: is_clear={analysis.is_clear}, type={analysis.problem_type}, confidence={analysis.confidence}")
        
    except Exception as e:
        logger.error(f"LLM error: {e}")
        
        # Track error count
        current_error_count = _get_attr(state, "llm_error_count", 0) + 1
        
        if current_error_count >= 3:
            # Too many errors - stop looping, inform user
            error_message = add_message(
                role="assistant",
                content="Atsiprašau, šiuo metu turime techninių nesklandumų. Prašome pabandyti vėliau arba susisiekti telefonu.",
                node="problem_capture"
            )
            return {
                "messages": [error_message],
                "current_node": "problem_capture",
                "last_error": str(e),
                "llm_error_count": current_error_count,
                "conversation_ended": True,  # Stop the conversation
            }
        
        # Fallback - ask generic question
        fallback_message = add_message(
            role="assistant",
            content="Atsiprašau, ar galėtumėte patikslinti savo problemą?",
            node="problem_capture"
        )
        return {
            "messages": [fallback_message],
            "current_node": "problem_capture",
            "last_error": str(e),
            "llm_error_count": current_error_count,
        }
    
    # Build response based on analysis
    if analysis.is_clear and analysis.confidence >= 0.7:
        # Problem understood - confirm and move on
        confirmation = f"Suprantu, turite {_translate_problem_type(analysis.problem_type)} problemą: {analysis.problem_description}. Patikrinsiu jūsų duomenis."
        
        message = add_message(
            role="assistant",
            content=confirmation,
            node="problem_capture"
        )
        
        return {
            "messages": [message],
            "current_node": "problem_capture",
            "problem_type": analysis.problem_type,
            "problem_description": analysis.problem_description,
        }
    else:
        # Need clarification
        question = analysis.clarification_question or "Ar galėtumėte plačiau papasakoti apie savo problemą?"
        
        message = add_message(
            role="assistant",
            content=question,
            node="problem_capture"
        )
        
        return {
            "messages": [message],
            "current_node": "problem_capture",
            # Partial info if available
            "problem_type": analysis.problem_type,
        }


def _translate_problem_type(problem_type: str | None) -> str:
    """Translate problem type to Lithuanian."""
    translations = {
        "internet": "interneto",
        "tv": "televizijos",
        "phone": "telefono",
        "other": "paslaugos"
    }
    return translations.get(problem_type, "paslaugos")


# === Router function ===

def problem_capture_router(state) -> str:
    """
    Route after problem capture.
    
    Returns:
        - "end" → conversation ended (error or resolved)
        - "problem_capture" → loop back (need more info)
        - "phone_lookup" → problem clear, continue workflow
    """
    # Check if conversation ended (due to error)
    if _get_attr(state, "conversation_ended", False):
        logger.info("Conversation ended, routing to END")
        return "end"
    
    problem_type = _get_attr(state, "problem_type")
    problem_description = _get_attr(state, "problem_description")
    
    if problem_type and problem_description:
        logger.info(f"Problem clear: {problem_type} - {problem_description}")
        return "phone_lookup"
    else:
        logger.info("Problem not clear, looping back")
        return "problem_capture"