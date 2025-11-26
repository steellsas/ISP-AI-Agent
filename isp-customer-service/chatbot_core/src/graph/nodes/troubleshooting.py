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
    selected_branch: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    needs_next_substep: bool = False  # ← NAUJAS
    next_substep_instruction: str | None = None  # ← NAUJAS


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


def format_step_instruction(step: dict, customer_name: str = "", is_first_time: bool = True) -> str:
    """
    Format step instruction for customer - ONE SUB-TASK AT A TIME.
    
    For phone conversations, we only give the FIRST action to do.
    """
    title = step.get("title", "")
    instruction = step.get("instruction", "")
    
    # Personalize if name available
    if customer_name:
        first_name = customer_name.split()[0]
        greeting = f"{first_name}, "
    else:
        greeting = ""
    
    if not is_first_time:
        return instruction
    
    # For first time - use LLM to extract only first action
    system_prompt = """Tu esi ISP klientų aptarnavimo asistentas telefono pokalbyje.

LABAI SVARBU:
- Tai telefoninis pokalbis - klientas negali matyti teksto
- Duok tik VIENĄ veiksmą per kartą
- Paprašyk padaryti vieną dalyką ir pasakyti rezultatą

Iš šios instrukcijos ištrauk tik PIRMĄ veiksmą kurį klientas turi padaryti:

{instruction}

Atsakyk trumpai ir aiškiai - tik pirmas veiksmas, vienas sakinys."""

    try:
        from src.services.llm import llm_completion
        
        messages = [
            {"role": "system", "content": system_prompt.format(instruction=instruction)},
            {"role": "user", "content": "Koks pirmas veiksmas?"}
        ]
        
        first_action = llm_completion(messages, temperature=0.2, max_tokens=150)
        return f"{greeting}{first_action}"
        
    except Exception as e:
        logger.warning(f"Could not simplify instruction: {e}")
        # Fallback - just return first 2 sentences
        sentences = instruction.split('. ')
        first_part = '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else instruction
        return f"{greeting}{first_part}"

def analyze_user_response(step: dict, user_response: str, recent_messages: list = None) -> StepResponse:
    """
    Use LLM to analyze user's response and guide step-by-step.
    
    For phone conversations - determines if we need more substeps
    or can move to next main step.
    
    Args:
        step: Current step data
        user_response: User's answer
        
    Returns:
        StepResponse with analysis
    """
    branches = step.get("branches", {})
    instruction = step.get("instruction", "")
    title = step.get("title", "")
    #Build conversation context
    conversation_context = ""
    if recent_messages:
        conversation_context = "ANKSTESNĖ POKALBIO DALIS (šiame žingsnyje):\n"
        for msg in recent_messages[-10:]:  # Last 10 messages
            role = "Agentas" if msg.get("role") == "assistant" else "Klientas"
            conversation_context += f"{role}: {msg.get('content', '')}\n"
        conversation_context += "\n---\n"
    
     # Build prompt for LLM
    system_prompt = f"""Tu esi ISP klientų aptarnavimo asistentas TELEFONO pokalbyje.

KONTEKSTAS:
- Tai telefoninis pokalbis - klientas NEGALI matyti ankstesnių žinučių
- Vesk klientą PO VIENĄ veiksmą - vienas veiksmas, vienas atsakymas
- Būk kantrus, aiškus, draugiškas
- SVARBU: Atsimink ką klientas JAU patikrino ir NEKARTOK tų pačių klausimų!

{conversation_context}

DABARTINIS ŽINGSNIS: {title}

PILNA INSTRUKCIJA (ką reikia patikrinti šiame žingsnyje):
{instruction}

GALIMI REZULTATAI kai žingsnis BAIGTAS:
{chr(10).join([f"- {branch_id}: {branch_data.get('condition')}" for branch_id, branch_data in branches.items()])}

DABAR KLIENTAS ATSAKĖ: "{user_response}"

TAVO UŽDUOTIS:
1. Peržiūrėk pokalbio istoriją - KAS JAU PATIKRINTA?
2. Ar klientas jau patikrino VISUS reikalingus dalykus šiam žingsniui?
3. Jei NE - paprašyk patikrinti TIK tai, kas DAR NEPATIKRINTA
4. Jei TAIP - pasirink tinkamą branch pagal rezultatus

SVARBU:
- Jei klientas jau sakė kad visos lemputes žalios - NEBEKLAUSINĖK apie lemputes!
- Jei klientas patikrino POWER, INTERNET, WiFi - žingsnis BAIGTAS
- Pasirink branch pagal VISUS gautus atsakymus

Atsakyk JSON formatu:
{{
    "understood": true,
    "user_answer_summary": "trumpai ką klientas pasakė/padarė",
    "selected_branch": "branch_id JEI žingsnis baigtas, ARBA null",
    "needs_clarification": false,
    "clarification_question": null,
    "needs_next_substep": true/false,
    "next_substep_instruction": "JEI reikia dar vieno veiksmo - trumpa instrukcija, ARBA null"
}}

PAVYZDŽIAI:

Jei pokalbio istorijoje jau yra: POWER=žalia, INTERNET=žalia, ir dabar WiFi=žalia:
{{
    "understood": true,
    "user_answer_summary": "WiFi lempute žalia. Visos lemputes žalios.",
    "selected_branch": "all_green",
    "needs_next_substep": false,
    "next_substep_instruction": null
}}

Jei POWER=žalia, bet INTERNET dar nepatikrintas:
{{
    "understood": true,
    "user_answer_summary": "POWER lempute žalia",
    "selected_branch": null,
    "needs_next_substep": true,
    "next_substep_instruction": "Puiku! Dabar patikrinkite INTERNET lempute - kokios ji spalvos?"
}}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_response}
    ]
    
    try:
        response = llm_json_completion(messages, temperature=0.3, max_tokens=400)
        return StepResponse(**response)
    except Exception as e:
        logger.error(f"Error analyzing response: {e}")
        return StepResponse(
            understood=False,
            user_answer_summary=user_response,
            needs_clarification=True,
            clarification_question="Atsiprašau, ar galėtumėte pakartoti ką matote?"
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
    
    # Check if problem already resolved - skip processing
    if _get_attr(state, "problem_resolved", False):
        logger.info("Problem already resolved - passing through to router")
        return {
            "current_node": "troubleshooting",
        }
    
    # Check if already needs escalation - skip processing
    if _get_attr(state, "troubleshooting_needs_escalation", False):
        logger.info("Already needs escalation - passing through to router")
        return {
            "current_node": "troubleshooting",
        }
    
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
                "troubleshooting_needs_escalation": True,
                "troubleshooting_escalation_reason": "scenario_not_found",
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
    
    # Get user response
    user_response = get_last_user_message(state)
    logger.info(f"Analyzing user response: {user_response}")
    
    # Check for goodbye/confirmation phrases BEFORE LLM analysis
    goodbye_phrases = [
        "ačiū", "aciu", "viso gero", "iki", "sudie",
        "viskas gerai", "nieko daugiau", "nereikia",
        "ne ačiū", "ne aciu", "ne, ačiū", "ne, aciu",
        "viskas", "pakanka", "užtenka"
    ]
    
    user_lower = user_response.lower()
    is_goodbye = any(phrase in user_lower for phrase in goodbye_phrases)
    
    # Check if problem was just resolved in previous turn
    # (user confirming everything is OK)
    messages = _get_messages(state)
    recent_assistant_msgs = [m for m in messages if m.get("role") == "assistant"][-3:]
    problem_just_resolved = any(
        "išspręsta" in m.get("content", "").lower() or
        "pavyko" in m.get("content", "").lower() or
        "veikia" in m.get("content", "").lower()
        for m in recent_assistant_msgs
    )
    
    if is_goodbye and problem_just_resolved:
        logger.info("User confirming goodbye after resolution → create_ticket (silent)")
        
        completed = ts_state.get("completed_steps", [])
        
        return {
            "current_node": "troubleshooting",
            "problem_resolved": True,
            "troubleshooting_completed_steps": completed,
        }
    
    # Load current scenario and step
    scenario_loader = get_scenario_loader()
    scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
    current_step = scenario.get_step(ts_state["current_step"])
    
    if not current_step:
        logger.error(f"Current step not found: {ts_state['current_step']}")
        return {
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "step_not_found",
        }
    
    # Get recent messages for context
    recent_ts_messages = [m for m in messages if m.get("node") == "troubleshooting"][-10:]
    
    # Analyze response with conversation context
    analysis = analyze_user_response(current_step, user_response, recent_ts_messages)
    
    logger.info(f"Analysis: branch={analysis.selected_branch}, needs_substep={analysis.needs_next_substep}, clarify={analysis.needs_clarification}")
    
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
    
    # Check if need to guide to next substep (step not yet complete)
    if analysis.needs_next_substep and analysis.next_substep_instruction:
        logger.info(f"Guiding to next substep within step {ts_state['current_step']}")
        
        message = add_message(
            role="assistant",
            content=analysis.next_substep_instruction,
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
    completed = ts_state.get("completed_steps", []) + [ts_state["current_step"]]
    
    if action == "resolved":
        # Problem resolved!
        logger.info("Problem resolved! → create_ticket (silent)")
        
        message = add_message(
            role="assistant",
            content=f"{branch_message}\n\nDžiaugiuosi, kad pavyko išspręsti problemą!",
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
        logger.info(f"Escalating: {selected_branch_data.get('reason')} → create_ticket")
        
        message = add_message(
            role="assistant",
            content=f"{branch_message}\n\nSukursiu techninės pagalbos užklausą.",
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
            message = add_message(
                role="assistant",
                content="Įvyko klaida scenarijuje. Sukursiu techninės pagalbos užklausą.",
                node="troubleshooting"
            )
            return {
                "messages": [message],
                "current_node": "troubleshooting",
                "troubleshooting_needs_escalation": True,
                "troubleshooting_escalation_reason": "next_step_not_found",
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
        # No branch matched - need to escalate
        logger.warning(f"No action or next_step for branch: {analysis.selected_branch}")
        
        message = add_message(
            role="assistant",
            content="Nepavyko automatiškai išspręsti problemos. Sukursiu techninės pagalbos užklausą.",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "no_matching_branch",
            "troubleshooting_completed_steps": completed,
        }


# def troubleshooting_router(state) -> str:
#     """
#     Route after troubleshooting.
    
#     Returns:
#         - "create_ticket" → create ticket (both resolved and escalation)
#         - "end" → wait for user response
#     """
#     problem_resolved = _get_attr(state, "problem_resolved", False)
#     needs_escalation = _get_attr(state, "troubleshooting_needs_escalation", False)
    
#     if problem_resolved:
#         logger.info("Problem resolved → create_ticket (silent)")
#         return "create_ticket"
    
#     if needs_escalation:
#         logger.info("Needs escalation → create_ticket (technician)")
#         return "create_ticket"
    
#     logger.info("Waiting for user response → end")
#     return "end"


def troubleshooting_router(state) -> str:
    """
    Route after troubleshooting.
    
    Returns:
        - "create_ticket" → create ticket (both resolved and escalation)
        - "end" → wait for user response
    """
    problem_resolved = _get_attr(state, "problem_resolved", False) 
    needs_escalation = _get_attr(state, "troubleshooting_needs_escalation", False)
    
    logger.info(f"Router: resolved={problem_resolved}, escalation={needs_escalation}")
    
    if problem_resolved:
        logger.info("→ create_ticket (resolved)")
        return "create_ticket"
    
    if needs_escalation:
        logger.info("→ create_ticket (escalation)")
        return "create_ticket"
    
    logger.info("→ end (waiting for user)")
    return "end"