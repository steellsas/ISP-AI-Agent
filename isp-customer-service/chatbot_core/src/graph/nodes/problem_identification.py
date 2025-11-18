"""
Problem Identification Node
Understand and categorize the customer's problem
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message, update_problem_info, get_last_user_message

logger = get_logger(__name__)


# Problem keywords by category (Lithuanian)
PROBLEM_KEYWORDS = {
    "internet_no_connection": [
        "neveikia", "nėra interneto", "nera interneto", "neprisijungia",
        "negali prisijungti", "no internet", "not working", "can't connect"
    ],
    "internet_slow": [
        "lėtas", "letas", "letai", "slow", "sulėtėjo", "suletejo",
        "vangus", "vangiai"
    ],
    "internet_intermittent": [
        "atsijungia", "nutrūksta", "nutruksta", "trūkinėja", "trukineja",
        "disconnects", "drops", "intermittent"
    ],
    "tv_no_signal": [
        "tv neveikia", "televizija neveikia", "nėra signalo", "nera signalo",
        "no signal", "juodas ekranas", "black screen"
    ],
    "tv_poor_quality": [
        "prasta kokybė", "prasta kokybe", "pikseliai", "braškėjimas", "braskejimas",
        "poor quality", "pixelated", "freezing"
    ],
    "equipment_issue": [
        "maršrutizatorius", "marsrutizatorius", "routeris", "router",
        "modem", "dekorius", "dekoderis", "decoder"
    ]
}


# Problem categories by type
PROBLEM_CATEGORIES = {
    "internet": [
        "internet_no_connection",
        "internet_slow", 
        "internet_intermittent"
    ],
    "tv": [
        "tv_no_signal",
        "tv_poor_quality"
    ],
    "equipment": [
        "equipment_issue"
    ]
}


def problem_identification_node(state: ConversationState) -> ConversationState:
    """
    Problem identification node - Categorize and understand the issue.
    
    This node:
    1. Analyzes user's problem description
    2. Categorizes the problem type and severity
    3. Extracts symptoms and affected devices
    4. Asks clarifying questions if needed
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with problem information
    """
    logger.info(f"[ProblemID] Processing for conversation {state['conversation_id']}")
    
    try:
        # Get last user message
        user_message = get_last_user_message(state)
        if not user_message:
            logger.warning("[ProblemID] No user message found")
            state = _request_problem_description(state)
            return state
        
        # Analyze problem from message
        problem_analysis = analyze_problem(user_message, state["language"])
        
        if not problem_analysis.get("problem_type"):
            logger.info("[ProblemID] Could not identify problem, requesting clarification")
            state = _request_problem_clarification(state)
            return state
        
        logger.info(f"[ProblemID] Identified problem: {problem_analysis}")
        
        # Update state with problem information
        problem_data = {
            "problem_type": problem_analysis["problem_type"],
            "category": problem_analysis.get("category"),
            "description": user_message,
            "symptoms": problem_analysis.get("symptoms", []),
        }
        
        state = update_problem_info(state, problem_data)
        
        # Create acknowledgment message
        language = state["language"]
        acknowledgment = _create_problem_acknowledgment(problem_analysis, language)
        state = add_message(state, "assistant", acknowledgment)
        
        # Ask clarifying questions if needed
        if problem_analysis.get("needs_clarification"):
            clarifying_question = _create_clarifying_question(problem_analysis, language)
            state = add_message(state, "assistant", clarifying_question)
        
        # state["current_node"] = "problem_identification"
        # logger.info(f"[ProblemID] Problem identified: {problem_data['problem_type']} - {problem_data['category']}")
        
        # return state
        if state["conversation_ended"]:
            state["current_node"] = "resolution"
        elif state["problem_identified"]:
            problem_type = state["problem"].get("problem_type")
            
            # Internet/TV problemos - į diagnostiką
            if problem_type in ["internet", "tv"]:
                state["current_node"] = "diagnostics"
            else:
                # Kitos problemos - tiesiai į troubleshooting
                state["current_node"] = "troubleshooting"
        else:
            # Jei neidentifikavo, vis tiek eina į troubleshooting
            state["current_node"] = "troubleshooting"

        return state
    except Exception as e:
        logger.error(f"[ProblemID] Error: {e}", exc_info=True)
        state = _handle_identification_error(state)
        return state


def analyze_problem(message: str, language: str = "lt") -> Dict[str, Any]:
    """
    Analyze problem description and categorize it.
    
    Args:
        message: User's problem description
        language: Language
        
    Returns:
        Dictionary with problem type, category, and symptoms
    """
    message_lower = message.lower()
    
    # Find matching category
    best_match = None
    best_score = 0
    matched_keywords = []
    
    for category, keywords in PROBLEM_KEYWORDS.items():
        score = 0
        category_keywords = []
        
        for keyword in keywords:
            if keyword in message_lower:
                score += 1
                category_keywords.append(keyword)
        
        if score > best_score:
            best_score = score
            best_match = category
            matched_keywords = category_keywords
    
    if not best_match:
        return {
            "problem_type": None,
            "category": None,
            "symptoms": [],
            "needs_clarification": True
        }
    
    # Determine problem type (internet, tv, phone)
    problem_type = None
    for ptype, categories in PROBLEM_CATEGORIES.items():
        if best_match in categories:
            problem_type = ptype
            break
    
    # Extract additional symptoms
    symptoms = _extract_symptoms(message_lower, best_match)
    
    # Determine if clarification is needed
    needs_clarification = best_score < 2 or not _has_enough_detail(message_lower)
    
    return {
        "problem_type": problem_type or "other",
        "category": best_match,
        "symptoms": symptoms,
        "matched_keywords": matched_keywords,
        "needs_clarification": needs_clarification
    }


def _extract_symptoms(message: str, category: str) -> List[str]:
    """Extract specific symptoms from message."""
    symptoms = []
    
    # Time-related
    if any(word in message for word in ["vakar", "šiandien", "yesterday", "today"]):
        symptoms.append("recent_onset")
    if any(word in message for word in ["visada", "nuolat", "constantly", "always"]):
        symptoms.append("persistent")
    
    # Device-related
    if any(word in message for word in ["visi", "viskas", "all", "everything"]):
        symptoms.append("affects_all_devices")
    if any(word in message for word in ["telefonas", "kompiuteris", "phone", "computer"]):
        symptoms.append("specific_device")
    
    # Severity
    if any(word in message for word in ["visai", "totally", "completely", "apskritai"]):
        symptoms.append("complete_failure")
    if any(word in message for word in ["kartais", "sometimes", "periodically"]):
        symptoms.append("intermittent")
    
    return symptoms


def _has_enough_detail(message: str) -> bool:
    """Check if message has enough detail about the problem."""
    # Consider detailed if message is longer and contains specific terms
    word_count = len(message.split())
    return word_count >= 5


def _request_problem_description(state: ConversationState) -> ConversationState:
    """Request problem description from customer."""
    language = state["language"]
    
    if language == "lt":
        message = """Papasakokite apie problemą:

• Internetas neveikia ar veikia lėtai?
• Televizija neveikia?
• Įranga nereaguoja?

Kuo daugiau informacijos pateiksite, tuo greičiau galėsiu padėti!"""
    else:
        message = """Tell me about the problem:

• Internet not working or slow?
• TV not working?
• Equipment not responding?

The more information you provide, the faster I can help!"""
    
    return add_message(state, "assistant", message)


def _request_problem_clarification(state: ConversationState) -> ConversationState:
    """Request problem clarification."""
    language = state["language"]
    
    if language == "lt":
        message = """Norėčiau geriau suprasti problemą.

Ar galėtumėte patikslinti:
• Kas tiksliai neveikia? (internetas / TV / kita)
• Kaip problema pasireiškia?
• Nuo kada tai vyksta?"""
    else:
        message = """I'd like to understand the problem better.

Could you clarify:
• What exactly is not working? (internet / TV / other)
• How does the problem manifest?
• Since when has this been happening?"""
    
    return add_message(state, "assistant", message)


def _create_problem_acknowledgment(
    problem_analysis: Dict[str, Any],
    language: str
) -> str:
    """Create acknowledgment message for identified problem."""
    problem_type = problem_analysis.get("problem_type")
    category = problem_analysis.get("category")
    
    # Problem descriptions
    descriptions = {
        "lt": {
            "internet_no_connection": "Internetas visai neveikia",
            "internet_slow": "Internetas veikia lėtai",
            "internet_intermittent": "Internetas nutrūkinėja",
            "tv_no_signal": "Televizija neveikia (nėra signalo)",
            "tv_poor_quality": "Televizijos vaizdas prastos kokybės",
            "equipment_issue": "Įrangos problema"
        },
        "en": {
            "internet_no_connection": "Internet is not working at all",
            "internet_slow": "Internet is slow",
            "internet_intermittent": "Internet keeps disconnecting",
            "tv_no_signal": "TV is not working (no signal)",
            "tv_poor_quality": "TV picture quality is poor",
            "equipment_issue": "Equipment issue"
        }
    }
    
    problem_desc = descriptions.get(language, descriptions["lt"]).get(
        category,
        "Techninė problema" if language == "lt" else "Technical problem"
    )
    
    if language == "lt":
        message = f"""Supratau - {problem_desc}. 

Dabar patikrinsiu tinklo būseną ir diagnostiką."""
    else:
        message = f"""I understand - {problem_desc}.

Let me check the network status and run diagnostics."""
    
    return message


def _create_clarifying_question(
    problem_analysis: Dict[str, Any],
    language: str
) -> str:
    """Create clarifying question based on problem type."""
    category = problem_analysis.get("category")
    
    questions = {
        "lt": {
            "internet_no_connection": "Ar indikatoriai ant maršrutizatoriaus šviečia?",
            "internet_slow": "Ar lėtai veikia visose programose ar tik tam tikrose?",
            "internet_intermittent": "Ar atsijungia tam tikru metu ar atsitiktinai?",
            "tv_no_signal": "Ar visi televizijos kanalai neveikia, ar tik kai kurie?",
            "tv_poor_quality": "Ar vaizdas pikseliuotas, ar tiesiog prastos kokybės?"
        },
        "en": {
            "internet_no_connection": "Are the lights on the router on?",
            "internet_slow": "Is it slow in all apps or just certain ones?",
            "internet_intermittent": "Does it disconnect at certain times or randomly?",
            "tv_no_signal": "Are all TV channels not working, or just some?",
            "tv_poor_quality": "Is the picture pixelated, or just poor quality?"
        }
    }
    
    return questions.get(language, questions["lt"]).get(category, "")


def _handle_identification_error(state: ConversationState) -> ConversationState:
    """Handle unexpected errors during problem identification."""
    language = state["language"]
    
    if language == "lt":
        message = """Atsiprašau, įvyko klaida analizuojant problemą.

Bet galiu pabandyti padėti! Ar galėtumėte trumpai aprašyti:
• Internetas neveikia?
• Televizija neveikia?"""
    else:
        message = """Sorry, an error occurred analyzing the problem.

But I can still try to help! Could you briefly describe:
• Internet not working?
• TV not working?"""
    
    return add_message(state, "assistant", message)
