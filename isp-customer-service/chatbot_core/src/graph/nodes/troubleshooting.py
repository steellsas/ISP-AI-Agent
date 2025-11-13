"""
Troubleshooting Node
Guide customer through troubleshooting steps with RAG-powered instructions
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger
from ..state import ConversationState, add_message, get_last_user_message

logger = get_logger(__name__)


# Basic troubleshooting steps by problem category
TROUBLESHOOTING_STEPS = {
    "internet_no_connection": [
        {
            "step": 1,
            "lt": "Patikrinkite, ar maršrutizatorius įjungtas ir ar šviečia indikatoriai",
            "en": "Check if the router is powered on and lights are on"
        },
        {
            "step": 2,
            "lt": "Pabandykite atjungti maršrutizatorių nuo maitinimo 30 sekundžių, tada vėl įjungti",
            "en": "Try unplugging the router for 30 seconds, then plug it back in"
        },
        {
            "step": 3,
            "lt": "Patikrinkite, ar tinklo kabelis tvirtai prijungtas prie maršrutizatoriaus ir kompiuterio",
            "en": "Check if network cable is firmly connected to router and computer"
        },
        {
            "step": 4,
            "lt": "Jei naudojate Wi-Fi, pabandykite prisijungti per tinklo kabelį",
            "en": "If using Wi-Fi, try connecting via network cable"
        }
    ],
    "internet_slow": [
        {
            "step": 1,
            "lt": "Uždarykite nereikalingas programas ir naršyklės korteles",
            "en": "Close unnecessary programs and browser tabs"
        },
        {
            "step": 2,
            "lt": "Patikrinkite, kiek įrenginių prisijungę prie tinklo - per daug įrenginių gali sulėtinti greitį",
            "en": "Check how many devices are connected - too many devices can slow down speed"
        },
        {
            "step": 3,
            "lt": "Perkraukite maršrutizatorių (atjunkite 30 sek., vėl įjunkite)",
            "en": "Restart the router (unplug 30 sec., plug back in)"
        },
        {
            "step": 4,
            "lt": "Jei naudojate Wi-Fi, pabandykite prisijungti per kabelį - tai turėtų būti greičiau",
            "en": "If using Wi-Fi, try connecting via cable - it should be faster"
        }
    ],
    "internet_intermittent": [
        {
            "step": 1,
            "lt": "Patikrinkite tinklo kabelių jungtis - galbūt kabelis atsilaisvinęs",
            "en": "Check network cable connections - cable might be loose"
        },
        {
            "step": 2,
            "lt": "Perkraukite maršrutizatorių",
            "en": "Restart the router"
        },
        {
            "step": 3,
            "lt": "Jei naudojate Wi-Fi, pabandykite priartėti prie maršrutizatoriaus",
            "en": "If using Wi-Fi, try moving closer to the router"
        }
    ],
    "tv_no_signal": [
        {
            "step": 1,
            "lt": "Patikrinkite, ar dekoderis įjungtas ir prijungtas prie elektros",
            "en": "Check if decoder is powered on and connected to electricity"
        },
        {
            "step": 2,
            "lt": "Patikrinkite HDMI ar scart kabelio jungtis tarp dekoderio ir televizoriaus",
            "en": "Check HDMI or scart cable connections between decoder and TV"
        },
        {
            "step": 3,
            "lt": "Perkraukite dekoderį (atjunkite nuo maitinimo 30 sek.)",
            "en": "Restart the decoder (unplug from power for 30 sec.)"
        },
        {
            "step": 4,
            "lt": "Patikrinkite, ar televizoriuje pasirinktas teisingas įvesties šaltinis (HDMI1, HDMI2 ir t.t.)",
            "en": "Check if correct input source is selected on TV (HDMI1, HDMI2, etc.)"
        }
    ],
    "tv_poor_quality": [
        {
            "step": 1,
            "lt": "Patikrinkite HDMI kabelio jungtis - ar tvirtai prijungta",
            "en": "Check HDMI cable connections - ensure firmly connected"
        },
        {
            "step": 2,
            "lt": "Perkraukite dekoderį",
            "en": "Restart the decoder"
        },
        {
            "step": 3,
            "lt": "Pabandykite kitus kanalus - ar problema yra visuose kanaluose",
            "en": "Try other channels - is the problem on all channels"
        }
    ]
}


def troubleshooting_node(state: ConversationState) -> ConversationState:
    """
    Troubleshooting node - Guide customer through problem-solving steps.
    
    This node:
    1. Retrieves appropriate troubleshooting steps from RAG
    2. Guides customer step-by-step
    3. Checks if problem is resolved after each step
    4. Determines if escalation is needed
    
    Args:
        state: Current conversation state
        
    Returns:
        Updated state with troubleshooting progress
    """
    logger.info(f"[Troubleshooting] Starting for conversation {state['conversation_id']}")
    
    try:
        language = state["language"]
        problem_category = state["problem"].get("category")
        troubleshooting = state["troubleshooting"]
        
        # Check if this is first troubleshooting attempt
        if not troubleshooting.get("steps_taken"):
            # Start new troubleshooting session
            state = _start_troubleshooting(state, problem_category, language)
        else:
            # Continue troubleshooting - check customer response
            user_message = get_last_user_message(state)
            state = _process_troubleshooting_response(state, user_message, language)
        
        state["current_node"] = "troubleshooting"
        state["troubleshooting_attempted"] = True
        
        return state
        
    except Exception as e:
        logger.error(f"[Troubleshooting] Error: {e}", exc_info=True)
        state = _handle_troubleshooting_error(state)
        return state


def _start_troubleshooting(
    state: ConversationState,
    problem_category: str,
    language: str
) -> ConversationState:
    """Start troubleshooting session with first step."""
    logger.info(f"[Troubleshooting] Starting session for {problem_category}")
    
    # Get troubleshooting steps
    steps = TROUBLESHOOTING_STEPS.get(problem_category, [])
    
    if not steps:
        # No specific steps for this problem
        state = _provide_general_troubleshooting(state, language)
        return state
    
    # TODO: Retrieve more detailed steps from RAG
    # rag_steps = retrieve_troubleshooting_steps(problem_category, language)
    
    # Start with first step
    first_step = steps[0]
    state["troubleshooting"]["steps_taken"] = []
    state["troubleshooting"]["current_step"] = 1
    state["troubleshooting"]["total_steps"] = len(steps)
    
    # Create instruction message
    if language == "lt":
        intro = f"""Gerai, pabandykime išspręsti problemą žingsnis po žingsnio.

**Žingsnis 1 iš {len(steps)}:**
{first_step['lt']}

Ar tai padėjo? Pasakykite "taip" jei problema išsisprendė, arba "ne" jei reikia toliau bandyti."""
    else:
        intro = f"""Okay, let's try to solve the problem step by step.

**Step 1 of {len(steps)}:**
{first_step['en']}

Did this help? Say "yes" if problem is solved, or "no" to continue trying."""
    
    state = add_message(state, "assistant", intro)
    state["troubleshooting"]["instructions_given"].append(first_step[language])
    
    return state


def _process_troubleshooting_response(
    state: ConversationState,
    user_message: str,
    language: str
) -> ConversationState:
    """Process customer's response to troubleshooting step."""
    
    if not user_message:
        return state
    
    message_lower = user_message.lower()
    
    # Check if problem is resolved
    positive_words = ["taip", "yes", "veikia", "works", "išspręsta", "solved", "padėjo", "helped"]
    negative_words = ["ne", "no", "neveikia", "not working", "nepadėjo", "didn't help"]
    
    is_resolved = any(word in message_lower for word in positive_words)
    needs_more_help = any(word in message_lower for word in negative_words)
    
    if is_resolved:
        state["troubleshooting"]["resolved"] = True
        state = _handle_problem_resolved(state, language)
        return state
    
    if needs_more_help or not is_resolved:
        # Continue to next step
        state["troubleshooting"]["customer_actions"].append(user_message)
        state = _continue_to_next_step(state, language)
        return state
    
    # Unclear response - ask for clarification
    state = _request_clarification(state, language)
    return state


def _continue_to_next_step(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Continue to next troubleshooting step."""
    
    current_step = state["troubleshooting"].get("current_step", 1)
    total_steps = state["troubleshooting"].get("total_steps", 0)
    problem_category = state["problem"].get("category")
    
    steps = TROUBLESHOOTING_STEPS.get(problem_category, [])
    
    # Check if we've exhausted all steps
    if current_step >= total_steps or current_step >= len(steps):
        state = _handle_steps_exhausted(state, language)
        return state
    
    # Move to next step
    next_step_num = current_step + 1
    next_step = steps[next_step_num - 1]  # 0-indexed
    
    state["troubleshooting"]["current_step"] = next_step_num
    state["troubleshooting"]["steps_taken"].append(current_step)
    
    if language == "lt":
        message = f"""Suprantu. Pabandykime kitą sprendimą.

**Žingsnis {next_step_num} iš {total_steps}:**
{next_step['lt']}

Ar tai padėjo?"""
    else:
        message = f"""I understand. Let's try another solution.

**Step {next_step_num} of {total_steps}:**
{next_step['en']}

Did this help?"""
    
    state = add_message(state, "assistant", message)
    state["troubleshooting"]["instructions_given"].append(next_step[language])
    
    logger.info(f"[Troubleshooting] Moved to step {next_step_num}/{total_steps}")
    
    return state


def _handle_problem_resolved(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Handle successful problem resolution."""
    logger.info("[Troubleshooting] Problem resolved!")
    
    if language == "lt":
        message = """Puiku! 🎉 Džiaugiuosi, kad problema išsisprendė!

Ar yra dar kažkas, kuo galėčiau padėti?"""
    else:
        message = """Great! 🎉 I'm glad the problem is resolved!

Is there anything else I can help you with?"""
    
    state = add_message(state, "assistant", message)
    state["troubleshooting"]["resolved"] = True
    
    return state


def _handle_steps_exhausted(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Handle case when all troubleshooting steps are exhausted."""
    logger.info("[Troubleshooting] All steps exhausted, escalating")
    
    state["requires_escalation"] = True
    state["next_action"] = "create_ticket"
    
    if language == "lt":
        message = """Išbandėme visus standartinius sprendimus, bet problema neišsisprendė.

Sukursiu gedimo pranešimą, ir mūsų technikas susisieks su Jumis artimiausiu metu.

Ar norite pridėti dar kokią nors informaciją į pranešimą?"""
    else:
        message = """We've tried all standard solutions, but the problem persists.

I'll create a support ticket, and our technician will contact you soon.

Would you like to add any additional information to the ticket?"""
    
    state = add_message(state, "assistant", message)
    
    return state


def _provide_general_troubleshooting(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Provide general troubleshooting when no specific steps available."""
    
    if language == "lt":
        message = """Pabandykime keletą bendrų sprendimų:

1. **Perkraukite įrangą** - atjunkite maršrutizatorių/dekoderių nuo maitinimo 30 sekundžių
2. **Patikrinkite kabelius** - ar visi kabeliai tvirtai prijungti
3. **Patikrinkite indikatorius** - ar šviečia lemputės ant įrangos

Ar kuris nors iš šių veiksmų padėjo?"""
    else:
        message = """Let's try some general solutions:

1. **Restart equipment** - unplug router/decoder for 30 seconds
2. **Check cables** - ensure all cables are firmly connected
3. **Check indicators** - are lights on the equipment lit

Did any of these actions help?"""
    
    state = add_message(state, "assistant", message)
    state["troubleshooting"]["instructions_given"].append("General troubleshooting steps")
    
    return state


def _request_clarification(
    state: ConversationState,
    language: str
) -> ConversationState:
    """Request clarification when response is unclear."""
    
    if language == "lt":
        message = """Atsiprašau, nevisiškai supratau.

Ar problema išsisprendė po šio žingsnio? Atsakykite "taip" arba "ne"."""
    else:
        message = """Sorry, I didn't fully understand.

Did the problem get resolved after this step? Please answer "yes" or "no"."""
    
    state = add_message(state, "assistant", message)
    return state


def _handle_troubleshooting_error(state: ConversationState) -> ConversationState:
    """Handle troubleshooting errors."""
    language = state["language"]
    
    if language == "lt":
        message = """Atsiprašau, įvyko klaida troubleshooting procese.

Geriausias sprendimas būtų sukurti gedimo pranešimą, kad technikas galėtų Jums padėti. Ar tinka?"""
    else:
        message = """Sorry, an error occurred in the troubleshooting process.

The best solution would be to create a support ticket so a technician can help you. Is that okay?"""
    
    state = add_message(state, "assistant", message)
    state["requires_escalation"] = True
    state["next_action"] = "create_ticket"
    
    return state
