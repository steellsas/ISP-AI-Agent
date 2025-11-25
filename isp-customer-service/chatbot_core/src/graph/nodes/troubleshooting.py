# """
# Troubleshooting Node
# Guide customer through troubleshooting steps with RAG-powered instructions
# """

# import sys
# from pathlib import Path
# from typing import Dict, Any, List, Optional

# # Add shared to path
# shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
# if str(shared_path) not in sys.path:
#     sys.path.insert(0, str(shared_path))

# from utils import get_logger
# from ..state import ConversationState, add_message, get_last_user_message

# logger = get_logger(__name__)


# # Basic troubleshooting steps by problem category
# TROUBLESHOOTING_STEPS = {
#     "internet_no_connection": [
#         {
#             "step": 1,
#             "lt": "Patikrinkite, ar maršrutizatorius įjungtas ir ar šviečia indikatoriai",
#             "en": "Check if the router is powered on and lights are on"
#         },
#         {
#             "step": 2,
#             "lt": "Pabandykite atjungti maršrutizatorių nuo maitinimo 30 sekundžių, tada vėl įjungti",
#             "en": "Try unplugging the router for 30 seconds, then plug it back in"
#         },
#         {
#             "step": 3,
#             "lt": "Patikrinkite, ar tinklo kabelis tvirtai prijungtas prie maršrutizatoriaus ir kompiuterio",
#             "en": "Check if network cable is firmly connected to router and computer"
#         },
#         {
#             "step": 4,
#             "lt": "Jei naudojate Wi-Fi, pabandykite prisijungti per tinklo kabelį",
#             "en": "If using Wi-Fi, try connecting via network cable"
#         }
#     ],
#     "internet_slow": [
#         {
#             "step": 1,
#             "lt": "Uždarykite nereikalingas programas ir naršyklės korteles",
#             "en": "Close unnecessary programs and browser tabs"
#         },
#         {
#             "step": 2,
#             "lt": "Patikrinkite, kiek įrenginių prisijungę prie tinklo - per daug įrenginių gali sulėtinti greitį",
#             "en": "Check how many devices are connected - too many devices can slow down speed"
#         },
#         {
#             "step": 3,
#             "lt": "Perkraukite maršrutizatorių (atjunkite 30 sek., vėl įjunkite)",
#             "en": "Restart the router (unplug 30 sec., plug back in)"
#         },
#         {
#             "step": 4,
#             "lt": "Jei naudojate Wi-Fi, pabandykite prisijungti per kabelį - tai turėtų būti greičiau",
#             "en": "If using Wi-Fi, try connecting via cable - it should be faster"
#         }
#     ],
#     "internet_intermittent": [
#         {
#             "step": 1,
#             "lt": "Patikrinkite tinklo kabelių jungtis - galbūt kabelis atsilaisvinęs",
#             "en": "Check network cable connections - cable might be loose"
#         },
#         {
#             "step": 2,
#             "lt": "Perkraukite maršrutizatorių",
#             "en": "Restart the router"
#         },
#         {
#             "step": 3,
#             "lt": "Jei naudojate Wi-Fi, pabandykite priartėti prie maršrutizatoriaus",
#             "en": "If using Wi-Fi, try moving closer to the router"
#         }
#     ],
#     "tv_no_signal": [
#         {
#             "step": 1,
#             "lt": "Patikrinkite, ar dekoderis įjungtas ir prijungtas prie elektros",
#             "en": "Check if decoder is powered on and connected to electricity"
#         },
#         {
#             "step": 2,
#             "lt": "Patikrinkite HDMI ar scart kabelio jungtis tarp dekoderio ir televizoriaus",
#             "en": "Check HDMI or scart cable connections between decoder and TV"
#         },
#         {
#             "step": 3,
#             "lt": "Perkraukite dekoderį (atjunkite nuo maitinimo 30 sek.)",
#             "en": "Restart the decoder (unplug from power for 30 sec.)"
#         },
#         {
#             "step": 4,
#             "lt": "Patikrinkite, ar televizoriuje pasirinktas teisingas įvesties šaltinis (HDMI1, HDMI2 ir t.t.)",
#             "en": "Check if correct input source is selected on TV (HDMI1, HDMI2, etc.)"
#         }
#     ],
#     "tv_poor_quality": [
#         {
#             "step": 1,
#             "lt": "Patikrinkite HDMI kabelio jungtis - ar tvirtai prijungta",
#             "en": "Check HDMI cable connections - ensure firmly connected"
#         },
#         {
#             "step": 2,
#             "lt": "Perkraukite dekoderį",
#             "en": "Restart the decoder"
#         },
#         {
#             "step": 3,
#             "lt": "Pabandykite kitus kanalus - ar problema yra visuose kanaluose",
#             "en": "Try other channels - is the problem on all channels"
#         }
#     ]
# }


# def troubleshooting_node(state: ConversationState) -> ConversationState:
#     """
#     Troubleshooting node - Guide customer through problem-solving steps.
    
#     This node:
#     1. Retrieves appropriate troubleshooting steps from RAG
#     2. Guides customer step-by-step
#     3. Checks if problem is resolved after each step
#     4. Determines if escalation is needed
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         Updated state with troubleshooting progress
#     """
#     logger.info(f"[Troubleshooting] Starting for conversation {state['conversation_id']}")
    
#     try:
#         language = state["language"]
#         problem_category = state["problem"].get("category")
#         troubleshooting = state["troubleshooting"]
        
#         # Check if this is first troubleshooting attempt
#         if not troubleshooting.get("steps_taken"):
#             # Start new troubleshooting session
#             state = _start_troubleshooting(state, problem_category, language)
#         else:
#             # Continue troubleshooting - check customer response
#             user_message = get_last_user_message(state)
#             state = _process_troubleshooting_response(state, user_message, language)
        
#         state["current_node"] = "troubleshooting"
#         state["troubleshooting_attempted"] = True
        
#         return state
        
#     except Exception as e:
#         logger.error(f"[Troubleshooting] Error: {e}", exc_info=True)
#         state = _handle_troubleshooting_error(state)
#         return state


# def _start_troubleshooting(
#     state: ConversationState,
#     problem_category: str,
#     language: str
# ) -> ConversationState:
#     """Start troubleshooting session with first step."""
#     logger.info(f"[Troubleshooting] Starting session for {problem_category}")
    
#     # Get troubleshooting steps
#     steps = TROUBLESHOOTING_STEPS.get(problem_category, [])
    
#     if not steps:
#         # No specific steps for this problem
#         state = _provide_general_troubleshooting(state, language)
#         return state
    
#     # TODO: Retrieve more detailed steps from RAG
#     # rag_steps = retrieve_troubleshooting_steps(problem_category, language)
    
#     # Start with first step
#     first_step = steps[0]
#     state["troubleshooting"]["steps_taken"] = []
#     state["troubleshooting"]["current_step"] = 1
#     state["troubleshooting"]["total_steps"] = len(steps)
    
#     # Create instruction message
#     if language == "lt":
#         intro = f"""Gerai, pabandykime išspręsti problemą žingsnis po žingsnio.

# **Žingsnis 1 iš {len(steps)}:**
# {first_step['lt']}

# Ar tai padėjo? Pasakykite "taip" jei problema išsisprendė, arba "ne" jei reikia toliau bandyti."""
#     else:
#         intro = f"""Okay, let's try to solve the problem step by step.

# **Step 1 of {len(steps)}:**
# {first_step['en']}

# Did this help? Say "yes" if problem is solved, or "no" to continue trying."""
    
#     state = add_message(state, "assistant", intro)
#     state["troubleshooting"]["instructions_given"].append(first_step[language])
    
#     return state


# def _process_troubleshooting_response(
#     state: ConversationState,
#     user_message: str,
#     language: str
# ) -> ConversationState:
#     """Process customer's response to troubleshooting step."""
    
#     if not user_message:
#         return state
    
#     message_lower = user_message.lower()
    
#     # Check if problem is resolved
#     positive_words = ["taip", "yes", "veikia", "works", "išspręsta", "solved", "padėjo", "helped"]
#     negative_words = ["ne", "no", "neveikia", "not working", "nepadėjo", "didn't help"]
    
#     is_resolved = any(word in message_lower for word in positive_words)
#     needs_more_help = any(word in message_lower for word in negative_words)
    
#     if is_resolved:
#         state["troubleshooting"]["resolved"] = True
#         state = _handle_problem_resolved(state, language)
#         return state
    
#     if needs_more_help or not is_resolved:
#         # Continue to next step
#         state["troubleshooting"]["customer_actions"].append(user_message)
#         state = _continue_to_next_step(state, language)
#         return state
    
#     # Unclear response - ask for clarification
#     state = _request_clarification(state, language)
#     return state


# def _continue_to_next_step(
#     state: ConversationState,
#     language: str
# ) -> ConversationState:
#     """Continue to next troubleshooting step."""
    
#     current_step = state["troubleshooting"].get("current_step", 1)
#     total_steps = state["troubleshooting"].get("total_steps", 0)
#     problem_category = state["problem"].get("category")
    
#     steps = TROUBLESHOOTING_STEPS.get(problem_category, [])
    
#     # Check if we've exhausted all steps
#     if current_step >= total_steps or current_step >= len(steps):
#         state = _handle_steps_exhausted(state, language)
#         return state
    
#     # Move to next step
#     next_step_num = current_step + 1
#     next_step = steps[next_step_num - 1]  # 0-indexed
    
#     state["troubleshooting"]["current_step"] = next_step_num
#     state["troubleshooting"]["steps_taken"].append(current_step)
    
#     if language == "lt":
#         message = f"""Suprantu. Pabandykime kitą sprendimą.

# **Žingsnis {next_step_num} iš {total_steps}:**
# {next_step['lt']}

# Ar tai padėjo?"""
#     else:
#         message = f"""I understand. Let's try another solution.

# **Step {next_step_num} of {total_steps}:**
# {next_step['en']}

# Did this help?"""
    
#     state = add_message(state, "assistant", message)
#     state["troubleshooting"]["instructions_given"].append(next_step[language])
    
#     logger.info(f"[Troubleshooting] Moved to step {next_step_num}/{total_steps}")
    
#     return state


# def _handle_problem_resolved(
#     state: ConversationState,
#     language: str
# ) -> ConversationState:
#     """Handle successful problem resolution."""
#     logger.info("[Troubleshooting] Problem resolved!")
    
#     if language == "lt":
#         message = """Puiku! 🎉 Džiaugiuosi, kad problema išsisprendė!

# Ar yra dar kažkas, kuo galėčiau padėti?"""
#     else:
#         message = """Great! 🎉 I'm glad the problem is resolved!

# Is there anything else I can help you with?"""
    
#     state = add_message(state, "assistant", message)
#     state["troubleshooting"]["resolved"] = True
    
#     return state


# def _handle_steps_exhausted(
#     state: ConversationState,
#     language: str
# ) -> ConversationState:
#     """Handle case when all troubleshooting steps are exhausted."""
#     logger.info("[Troubleshooting] All steps exhausted, escalating")
    
#     state["requires_escalation"] = True
#     state["next_action"] = "create_ticket"
    
#     if language == "lt":
#         message = """Išbandėme visus standartinius sprendimus, bet problema neišsisprendė.

# Sukursiu gedimo pranešimą, ir mūsų technikas susisieks su Jumis artimiausiu metu.

# Ar norite pridėti dar kokią nors informaciją į pranešimą?"""
#     else:
#         message = """We've tried all standard solutions, but the problem persists.

# I'll create a support ticket, and our technician will contact you soon.

# Would you like to add any additional information to the ticket?"""
    
#     state = add_message(state, "assistant", message)
    
#     return state


# def _provide_general_troubleshooting(
#     state: ConversationState,
#     language: str
# ) -> ConversationState:
#     """Provide general troubleshooting when no specific steps available."""
    
#     if language == "lt":
#         message = """Pabandykime keletą bendrų sprendimų:

# 1. **Perkraukite įrangą** - atjunkite maršrutizatorių/dekoderių nuo maitinimo 30 sekundžių
# 2. **Patikrinkite kabelius** - ar visi kabeliai tvirtai prijungti
# 3. **Patikrinkite indikatorius** - ar šviečia lemputės ant įrangos

# Ar kuris nors iš šių veiksmų padėjo?"""
#     else:
#         message = """Let's try some general solutions:

# 1. **Restart equipment** - unplug router/decoder for 30 seconds
# 2. **Check cables** - ensure all cables are firmly connected
# 3. **Check indicators** - are lights on the equipment lit

# Did any of these actions help?"""
    
#     state = add_message(state, "assistant", message)
#     state["troubleshooting"]["instructions_given"].append("General troubleshooting steps")
    
#     return state


# def _request_clarification(
#     state: ConversationState,
#     language: str
# ) -> ConversationState:
#     """Request clarification when response is unclear."""
    
#     if language == "lt":
#         message = """Atsiprašau, nevisiškai supratau.

# Ar problema išsisprendė po šio žingsnio? Atsakykite "taip" arba "ne"."""
#     else:
#         message = """Sorry, I didn't fully understand.

# Did the problem get resolved after this step? Please answer "yes" or "no"."""
    
#     state = add_message(state, "assistant", message)
#     return state


# def _handle_troubleshooting_error(state: ConversationState) -> ConversationState:
#     """Handle troubleshooting errors."""
#     language = state["language"]
    
#     if language == "lt":
#         message = """Atsiprašau, įvyko klaida troubleshooting procese.

# Geriausias sprendimas būtų sukurti gedimo pranešimą, kad technikas galėtų Jums padėti. Ar tinka?"""
#     else:
#         message = """Sorry, an error occurred in the troubleshooting process.

# The best solution would be to create a support ticket so a technician can help you. Is that okay?"""
    
#     state = add_message(state, "assistant", message)
#     state["requires_escalation"] = True
#     state["next_action"] = "create_ticket"
    
#     return state
"""
Troubleshooting Node - Guided customer troubleshooting with scenarios
"""

import sys
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import Literal

# Try shared logger
try:
    shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
    if str(shared_path) not in sys.path:
        sys.path.insert(0, str(shared_path))
    from utils import get_logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    def get_logger(name):
        return logging.getLogger(name)

# Add RAG path
rag_path = Path(__file__).parent.parent.parent / "rag"
if str(rag_path) not in sys.path:
    sys.path.insert(0, str(rag_path))

from src.rag.scenario_loader import get_scenario_loader  # ← Pridėti rag.
from src.rag.retriever import get_retriever              # ← Pridėti rag.

from src.services.llm import llm_json_completion
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = get_logger(__name__)


# === LLM Response Schemas ===

class ScenarioSelection(BaseModel):
    """LLM response for selecting scenario."""
    scenario_id: str
    confidence: float  # 0-1
    reasoning: str


class StepResponse(BaseModel):
    """LLM response for analyzing user answer to troubleshooting step."""
    understood: bool
    user_answer_summary: str
    selected_branch: str | None = None  # e.g., "no_lights", "working"
    needs_clarification: bool = False
    clarification_question: str | None = None


# === Helper Functions ===

def _get_troubleshooting_state(state) -> dict:
    """Get troubleshooting state from conversation state."""
    scenario_id = _get_attr(state, "troubleshooting_scenario_id")
    current_step = _get_attr(state, "troubleshooting_current_step")
    completed_steps = _get_attr(state, "troubleshooting_completed_steps")
    
    return {
        "scenario_id": scenario_id,
        "current_step": current_step if current_step else 1,
        "completed_steps": completed_steps if completed_steps else [],
    }


def select_scenario(problem_description: str, problem_type: str) -> str:
    """
    Select appropriate troubleshooting scenario using RAG.
    
    Args:
        problem_description: User's problem description
        problem_type: Problem type (internet, tv, phone)
        
    Returns:
        Scenario ID
    """
    logger.info(f"Selecting scenario for: {problem_description} (type: {problem_type})")
    
    # Use retriever to find best matching scenario
    retriever = get_retriever()
    
    # Load production KB
    try:
        success = retriever.load("production")
        if success:
            logger.info("Loaded production knowledge base")
        else:
            logger.warning("Could not load production KB")
    except Exception as e:
        logger.error(f"Error loading production KB: {e}")
    
    query = f"{problem_type} {problem_description}"
    results = retriever.retrieve(
        query=query,
        top_k=3,
        threshold=0.5,
        filter_metadata={"type": "scenario", "problem_type": problem_type}
    )
    
    if results:
        best_match = results[0]
        scenario_id = best_match["metadata"]["scenario_id"]
        logger.info(f"Selected scenario: {scenario_id} (score: {best_match['score']:.3f})")
        return scenario_id
    
    # Fallback to default based on problem type
    logger.warning(f"No scenario found for {problem_type}, using default")
    return f"{problem_type}_no_connection"


def format_step_instruction(step: dict, customer_name: str = "") -> str:
    """Format step instruction for customer."""
    title = step.get("title", "")
    instruction = step.get("instruction", "")
    
    # Personalize if name available
    if customer_name:
        first_name = customer_name.split()[0]
        greeting = f"{first_name}, "
    else:
        greeting = ""
    
    message = f"{greeting}{instruction}"
    return message


def analyze_user_response(step: dict, user_response: str) -> StepResponse:
    """
    Use LLM to analyze user's response and determine which branch to take.
    
    Args:
        step: Current step data
        user_response: User's answer
        
    Returns:
        StepResponse with analysis
    """
    branches = step.get("branches", {})
    
    # Build prompt for LLM
    system_prompt = f"""Tu esi ISP klientų aptarnavimo asistentas.
Klientas atlieka troubleshooting žingsnį: {step.get('title')}

Instrukcija buvo: {step.get('instruction')}

Galimi atsakymo variantai (branches):
{chr(10).join([f"- {branch_id}: {branch_data.get('condition')}" for branch_id, branch_data in branches.items()])}

Analizuok kliento atsakymą ir nuspręsk:
1. Ar supratai ką klientas atsakė?
2. Kuris branch geriausiai atitinka?
3. Ar reikia patikslinti?

Atsakyk JSON formatu:
{{
    "understood": true | false,
    "user_answer_summary": "trumpas kliento atsakymo aprašymas",
    "selected_branch": "branch_id arba null",
    "needs_clarification": true | false,
    "clarification_question": "klausimas jei reikia patikslinti, arba null"
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_response}
    ]
    
    try:
        response = llm_json_completion(messages, temperature=0.2, max_tokens=300)
        return StepResponse(**response)
    except Exception as e:
        logger.error(f"Error analyzing response: {e}")
        # Fallback
        return StepResponse(
            understood=False,
            user_answer_summary=user_response,
            needs_clarification=True,
            clarification_question="Atsiprašau, ar galėtumėte pakartoti savo atsakymą?"
        )


# === Node Functions ===

def troubleshooting_node(state) -> dict:
    """
    Troubleshooting node - guides customer through troubleshooting steps.
    
    Flow:
    1. First time: Select scenario and start step 1
    2. Subsequent: Analyze user response, move to next step or resolve
    
    Args:
        state: Current conversation state
        
    Returns:
        State update dict
    """
    logger.info("=== Troubleshooting Node ===")
    
    ts_state = _get_troubleshooting_state(state)
    problem_description = _get_attr(state, "problem_description", "")
    problem_type = _get_attr(state, "problem_type", "internet")
    customer_name = _get_attr(state, "customer_name", "")
    
    # Check if first time in troubleshooting
    if not ts_state["scenario_id"]:
        logger.info("First time in troubleshooting - selecting scenario")
        
        # Select scenario
        scenario_id = select_scenario(problem_description, problem_type)
        
        # Load scenario
        scenario_loader = get_scenario_loader()
        scenario = scenario_loader.get_scenario(scenario_id)
        
        if not scenario:
            logger.error(f"Scenario not found: {scenario_id}")
            error_msg = add_message(
                role="assistant",
                content="Atsiprašau, nepavyko rasti tinkamo sprendimo scenarijaus. Sukursiu techninės pagalbos užklausą.",
                node="troubleshooting"
            )
            return {
                "messages": [error_msg],
                "current_node": "troubleshooting",
                "troubleshooting_failed": True,
            }
        
        # Get first step
        first_step = scenario.get_first_step()
        
        # Format instruction
        instruction_text = format_step_instruction(first_step, customer_name)
        
        message = add_message(
            role="assistant",
            content=f"Gerai, pabandykime išspręsti problemą kartu.\n\n**{first_step.get('title')}**\n\n{instruction_text}",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_scenario_id": scenario_id,
            "troubleshooting_current_step": first_step.get("step_id"),
            "troubleshooting_completed_steps": [],
        }
    
    # Analyze user response to current step
    user_response = get_last_user_message(state)
    logger.info(f"Analyzing user response: {user_response}")
    
    # Load current scenario and step
    scenario_loader = get_scenario_loader()
    scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
    current_step = scenario.get_step(ts_state["current_step"])
    
    # Analyze response
    analysis = analyze_user_response(current_step, user_response)
    
    if analysis.needs_clarification:
        # Ask for clarification
        message = add_message(
            role="assistant",
            content=analysis.clarification_question,
            node="troubleshooting"
        )
        return {
            "messages": [message],
            "current_node": "troubleshooting",
        }
    
    # Determine next action based on selected branch
    branches = current_step.get("branches", {})
    selected_branch_data = branches.get(analysis.selected_branch, {})
    
    action = selected_branch_data.get("action")
    next_step_id = selected_branch_data.get("next_step")
    branch_message = selected_branch_data.get("message", "")
    
    # Update completed steps
    completed = ts_state["completed_steps"] + [ts_state["current_step"]]
    
    if action == "resolved":
        # Problem resolved!
        logger.info("Problem resolved!")
        
        message = add_message(
            role="assistant",
            content=f"{branch_message}\n\nDžiaugiuosi, kad pavyko išspręsti problemą! Ar yra dar kažkas, kuo galėčiau padėti?",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "problem_resolved": True,
            "troubleshooting_completed_steps": completed,
        }
    
    elif action == "escalate":
        # Need technician
        logger.info(f"Escalating: {selected_branch_data.get('reason')}")
        
        message = add_message(
            role="assistant",
            content=f"{branch_message}\n\nSukursiu techninės pagalbos užklausą su visais mūsų atliktais žingsniais.",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": selected_branch_data.get("reason"),
            "troubleshooting_completed_steps": completed,
        }
    
    elif next_step_id:
        # Move to next step
        next_step = scenario.get_step(next_step_id)
        
        if not next_step:
            logger.error(f"Next step not found: {next_step_id}")
            # Fallback to escalation
            message = add_message(
                role="assistant",
                content="Įvyko klaida scenarijuje. Sukursiu techninės pagalbos užklausą.",
                node="troubleshooting"
            )
            return {
                "messages": [message],
                "current_node": "troubleshooting",
                "troubleshooting_needs_escalation": True,
                "troubleshooting_completed_steps": completed,
            }
        
        # Format next step
        instruction_text = format_step_instruction(next_step, customer_name)
        
        message = add_message(
            role="assistant",
            content=f"{branch_message}\n\n**{next_step.get('title')}**\n\n{instruction_text}",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_current_step": next_step_id,
            "troubleshooting_completed_steps": completed,
        }
    
    else:
        # Unexpected - escalate
        logger.warning("No action or next_step defined")
        message = add_message(
            role="assistant",
            content="Sukursiu techninės pagalbos užklausą.",
            node="troubleshooting"
        )
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_completed_steps": completed,
        }


def troubleshooting_router(state) -> str:
    """
    Route after troubleshooting.
    
    Returns:
        - "troubleshooting" → continue troubleshooting (loop)
        - "create_ticket" → escalate to technician
        - "closing" → problem resolved, end conversation
        - "end" → wait for user response
    """
    problem_resolved = _get_attr(state, "problem_resolved", False)
    needs_escalation = _get_attr(state, "troubleshooting_needs_escalation", False)
    
    if problem_resolved:
        logger.info("Problem resolved → closing")
        return "closing"
    
    if needs_escalation:
        logger.info("Needs escalation → create_ticket")
        return "create_ticket"
    
    # Continue troubleshooting - wait for user response
    logger.info("Waiting for user response → end")
    return "end"