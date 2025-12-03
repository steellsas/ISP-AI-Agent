
"""
Troubleshooting Node v3 - Guided customer troubleshooting with scenarios

Integrates with problem_context to:
1. Skip steps customer already tried
2. Start from appropriate step based on known info
3. Inform LLM about prior context

Supports multiple languages via translation service.
"""

import logging
from typing import Any, Literal
from pydantic import BaseModel

from src.rag.scenario_loader import get_scenario_loader
from src.rag import get_hybrid_retriever, get_retriever

from src.services.llm import llm_json_completion, llm_completion
from src.services.language_service import get_language, get_language_name
from src.services.translation_service import t, t_list
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = logging.getLogger(__name__)


# =============================================================================
# LLM RESPONSE SCHEMAS
# =============================================================================

class StepResponse(BaseModel):
    """LLM response for analyzing user answer to troubleshooting step."""
    understood: bool
    user_answer_summary: str
    selected_branch: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    needs_next_substep: bool = False
    problem_resolved: bool = False


class ResolutionCheck(BaseModel):
    """LLM response for checking if problem is resolved."""
    is_resolved: bool
    confidence: float
    user_says_working: bool
    user_says_not_working: bool
    needs_confirmation: bool
    response_message: str

def translate_step_content(text: str, content_type: str = "title", conversation_id: str = "") -> str:
    """
    Translate step title/instruction to current UI language.
    
    YAML scenarios are in Lithuanian. If UI language is English, 
    we translate on-the-fly using LLM.
    """
    if not text:
        return text
    
    # If UI is Lithuanian, no translation needed
    current_lang = get_language()  # Returns "lt" or "en"
    if current_lang == "lt":
        return text
    
    # Get target language name for prompt
    target_language = get_language_name()  # Returns "Lithuanian" or "English"
    
    # Quick translation using LLM
    try:
        if content_type == "title":
            prompt = f"""Translate this step title to {target_language}. 
Keep it short and clear (max 6-8 words).

Lithuanian: {text}
{target_language}:"""
        else:
            prompt = f"""Translate this instruction to {target_language}.
Keep it natural and conversational.

Lithuanian: {text}
{target_language}:"""
        
        messages = [{"role": "user", "content": prompt}]
        translated = llm_completion(messages, temperature=0.1, max_tokens=100)
        
        # Clean up response
        translated = translated.strip().strip('"').strip("'")
        
        logger.debug(f"[{conversation_id}] Translated '{text[:30]}...' -> '{translated[:30]}...'")
        return translated
        
    except Exception as e:
        logger.warning(f"[{conversation_id}] Translation failed: {e} - using original")
        return text

# =============================================================================
# HELP REQUEST DETECTION
# =============================================================================

def detect_help_request(user_message: str) -> bool:
    """
    Detect if user is asking for help with current instruction.
    """
    msg_lower = user_message.lower().strip()
    
    # Get help phrases from translations
    help_phrases = (
        t_list("help_request.general") +
        t_list("help_request.location") +
        t_list("help_request.meaning") +
        t_list("help_request.how_to")
    )
    
    if any(phrase in msg_lower for phrase in help_phrases):
        return True
    
    confused = t_list("help_request.confused")
    if msg_lower in confused or msg_lower in ["?", "??", "kas", "kur", "kaip"]:
        return True
    
    return False


def generate_help_response(current_step: dict, conversation_id: str = "") -> str:
    """Generate detailed help instructions for current step."""
    step_title = current_step.get("title", "")
    step_instruction = current_step.get("instruction", "")
    output_language = get_language_name()
    
    logger.info(f"[{conversation_id}] Generating help for step: {step_title[:30]}...")
    
    system_prompt = f"""You are an ISP customer service assistant on a phone call.
The customer needs help understanding a troubleshooting step.

Step title: {step_title}
Step instruction: {step_instruction}

Generate a helpful, detailed explanation that:
1. Explains what they need to do step by step
2. Tells them WHERE to find things
3. Uses simple language for non-technical users
4. Ends with a question to check if they succeeded

CRITICAL: Respond ONLY in {output_language} language.
Be friendly and patient."""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Help me understand this step."}
        ]
        
        return llm_completion(messages, temperature=0.3, max_tokens=400)
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Help generation error: {e}")
        return t(
            "troubleshooting.help_generic",
            step_title=step_title,
            instruction=step_instruction
        )


# =============================================================================
# FRUSTRATION DETECTION
# =============================================================================

def detect_frustration(user_message: str) -> dict:
    """Detect if user is frustrated, annoyed, or pointing out bot mistakes."""
    msg_lower = user_message.lower().strip()
    
    frustration_phrases = t_list("frustration.general") + t_list("frustration.give_up")
    repetition_phrases = t_list("frustration.repetition")
    escalation_phrases = t_list("frustration.escalation")
    
    is_frustrated = any(phrase in msg_lower for phrase in frustration_phrases)
    is_repetition_complaint = any(phrase in msg_lower for phrase in repetition_phrases)
    wants_escalation = any(phrase in msg_lower for phrase in escalation_phrases)
    
    severity = 0
    if is_repetition_complaint:
        severity += 1
    if is_frustrated:
        severity += 2
    if wants_escalation:
        severity += 3
    
    return {
        "is_frustrated": is_frustrated,
        "is_repetition_complaint": is_repetition_complaint,
        "wants_escalation": wants_escalation,
        "severity": severity,
        "should_apologize": is_frustrated or is_repetition_complaint,
        "should_summarize": is_repetition_complaint,
        "should_escalate": wants_escalation or severity >= 4,
    }


def generate_apology_response(frustration: dict, checked_items: dict, problem_description: str) -> str:
    """Generate appropriate apology response based on frustration type."""
    summary_parts = []
    if checked_items:
        if "router_lights" in checked_items:
            summary_parts.append(f"router lights: {checked_items['router_lights']}")
        if checked_items.get("router_restarted"):
            summary_parts.append("router restarted")
        if "wifi_status" in checked_items:
            summary_parts.append(f"WiFi: {checked_items['wifi_status']}")
    
    summary = ", ".join(summary_parts) if summary_parts else problem_description
    
    if frustration.get("is_repetition_complaint"):
        checked = summary if summary_parts else "basic checks"
        return t("troubleshooting.apology_repetition", problem=problem_description, checked=checked)
    
    if frustration.get("is_frustrated"):
        return t("troubleshooting.apology_frustration", summary=summary)
    
    if frustration.get("wants_escalation"):
        return t("troubleshooting.offer_escalation")
    
    return t("errors.general")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_troubleshooting_state(state: Any) -> dict:
    """Get troubleshooting state from conversation state."""
    return {
        "scenario_id": _get_attr(state, "troubleshooting_scenario_id"),
        "current_step": _get_attr(state, "troubleshooting_current_step") or 1,
        "completed_steps": _get_attr(state, "troubleshooting_completed_steps") or [],
        "skipped_steps": _get_attr(state, "troubleshooting_skipped_steps") or [],
        "checked_items": _get_attr(state, "troubleshooting_checked_items") or {},
    }


# =============================================================================
# CONTEXT & SMART ROUTING FUNCTIONS (from V2)
# =============================================================================

def build_context_summary(problem_context: dict, problem_type: str) -> str:
    """
    Build human-readable summary of what we know from problem_context.
    This helps LLM understand what was already discussed.
    """
    if not problem_context:
        return ""
    
    summary_parts = []
    
    # Duration
    duration = problem_context.get("duration")
    if duration:
        summary_parts.append(f"Problem started: {duration}")
    
    # Scope - CRITICAL for routing
    scope = problem_context.get("scope")
    if scope:
        scope_lower = str(scope).lower()
        if any(kw in scope_lower for kw in ["visi", "visur", "visuose", "all"]):
            summary_parts.append("⚠️ Problem affects ALL devices")
        elif any(kw in scope_lower for kw in ["telefon", "phone", "vienas", "one", "laptop", "kompiuter"]):
            summary_parts.append("⚠️ Problem affects SINGLE DEVICE ONLY - router likely OK!")
        else:
            summary_parts.append(f"Affected: {scope}")
    
    # Restart attempt
    tried_restart = problem_context.get("tried_restart")
    if tried_restart is True:
        summary_parts.append("🔴 Customer ALREADY tried restarting router - DON'T ASK AGAIN!")
    elif tried_restart is False:
        summary_parts.append("Customer has NOT tried restarting router yet")
    
    # Router lights
    router_lights = problem_context.get("router_lights")
    if router_lights:
        summary_parts.append(f"Router lights: {router_lights}")
    
    # WiFi visibility
    wifi_visible = problem_context.get("wifi_visible")
    if wifi_visible is True:
        summary_parts.append("Customer can see WiFi network")
    elif wifi_visible is False:
        summary_parts.append("Customer CANNOT see WiFi network")
    
    if not summary_parts:
        return ""
    
    return "KNOWN INFORMATION FROM EARLIER:\n- " + "\n- ".join(summary_parts)


def determine_starting_step(scenario, problem_context: dict, problem_type: str, diagnostic_results: dict = None, conversation_id: str = "") -> tuple:
    """
    Determine which step to start from based on problem_context AND diagnostic_results.
    
    Smart routing logic:
    1. If diagnostics confirm router is working → skip router steps
    2. If problem affects single device only → skip router steps  
    3. If customer already tried something → skip that step
    
    Returns:
        tuple: (starting_step, skipped_steps_list, skip_reason_message)
    """
    first_step = scenario.get_first_step()
    skipped_steps = []
    skip_message = ""
    
    # ===========================================
    # PRIORITY 1: Check diagnostic_results
    # ===========================================
    if diagnostic_results:
        ip_check = diagnostic_results.get("ip_assignment_check", {})
        port_check = diagnostic_results.get("port_status_check", {})
        
        # Router confirmed working if IP assigned and port up
        ip_active = ip_check.get("success") and ip_check.get("active_count", 0) > 0
        port_healthy = port_check.get("diagnostics", {}).get("all_ports_healthy", False)
        
        if ip_active and port_healthy:
            logger.info(f"[{conversation_id}] ✅ Diagnostics confirm router is working - can skip router checks")
    
    # ===========================================
    # PRIORITY 2: Check scope (SINGLE DEVICE = skip router)
    # ===========================================
    if problem_context:
        scope = str(problem_context.get("scope", "")).lower()
        single_device_keywords = ["telefonas", "telefone", "phone", "kompiuteris", "laptop", "vienas", "tik vienas", "one device"]
        
        is_single_device = any(kw in scope for kw in single_device_keywords)
        
        if is_single_device:
            logger.info(f"[{conversation_id}] ✅ Single device affected: '{scope}' - skipping to device check (step 4)")
            
            # Try to get step 4 (WiFi/device check)
            device_step = scenario.get_step(4)
            if device_step:
                skipped_steps = [1, 2, 3]
                skip_message = t("troubleshooting.skip_single_device")
                return device_step, skipped_steps, skip_message
    
    # ===========================================
    # PRIORITY 3: Check if customer already tried restart
    # ===========================================
    if problem_context:
        tried_restart = problem_context.get("tried_restart")
        
        if tried_restart is True:
            logger.info(f"[{conversation_id}] ✅ Customer already tried restart - skip restart step")
            # If step 5 is restart, we should note this but still check lights first
            skip_message = t("troubleshooting.skip_restart_tried")
    
    # ===========================================
    # PRIORITY 4: Check known router_lights
    # ===========================================
    if problem_context:
        router_lights = problem_context.get("router_lights")
        if router_lights:
            lights_lower = str(router_lights).lower()
            
            # If lights already known to be green → skip to step 4
            if any(kw in lights_lower for kw in ["žalia", "green", "dega", "visos"]):
                logger.info(f"[{conversation_id}] ✅ Router lights already known: {router_lights} - skip to device check")
                device_step = scenario.get_step(4)
                if device_step:
                    skipped_steps = [1, 2, 3]
                    skip_message = t("troubleshooting.skip_lights_checked")
                    return device_step, skipped_steps, skip_message
    
    # Default: start from first step
    return first_step, skipped_steps, skip_message


# def get_smart_scenario_id(problem_type: str, problem_context: dict, diagnostic_results: dict = None) -> str:
#     """
#     Select the most appropriate scenario based on context.
    
#     Smart routing:
#     - Single device problem → internet_single_device (device-first approach)
#     - All devices problem → internet_no_connection (router-first approach)
#     """
#     if problem_type != "internet":
#         # For non-internet problems, use default scenarios
#         default_scenarios = {
#             "tv": "tv_no_signal",
#             "phone": "internet_no_connection",  # fallback
#             "other": "internet_no_connection",
#         }
#         return default_scenarios.get(problem_type, "internet_no_connection")
    
#     # For internet problems, check scope to determine best scenario
#     if problem_context:
#         scope = str(problem_context.get("scope", "")).lower()
        
#         # Single device keywords - use device-first scenario
#         single_device_keywords = [
#             "telefonas", "telefone", "phone", 
#             "vienas", "viename", "tik vienas",
#             "laptop", "kompiuteris", "kompiuteryje",
#             "tablet", "planšetė"
#         ]
        
#         if any(kw in scope for kw in single_device_keywords):
#             # Try to use single device scenario if available
#             # Will fallback to internet_no_connection if scenario not loaded
#             logger.info(f"Smart routing: Single device detected ('{scope}') → internet_single_device")
#             return "internet_single_device"
        
#         # All devices affected - router-first approach
#         all_devices_keywords = ["visi", "visur", "visuose", "all", "viskas"]
#         if any(kw in scope for kw in all_devices_keywords):
#             logger.info(f"Smart routing: All devices affected ('{scope}') → internet_no_connection")
#             return "internet_no_connection"
    
#     # Default fallback
#     return "internet_no_connection"


def get_smart_scenario_id(
    problem_type: str, 
    problem_context: dict, 
    problem_description: str = "",
    diagnostic_results: dict = None, 
    conversation_id: str = ""
) -> str:
    """
    Hybrid scenario selection: Smart routing + Context-aware RAG.
    
    Priority:
    1. Instant routing for clear single-device cases (fastest)
    2. Context-enriched RAG search for complex cases
    3. Default fallback
    """
    
    # ===========================================
    # PRIORITY 1: Instant routing (no RAG needed)
    # ===========================================
    if problem_context and problem_type == "internet":
        scope = str(problem_context.get("scope", "")).lower()
        
        single_device_keywords = [
            "telefonas", "telefone", "phone", 
            "vienas", "viename", "tik vienas",
            "laptop", "kompiuteris", "kompiuteryje",
            "tablet", "planšetė"
        ]
        
        if any(kw in scope for kw in single_device_keywords):
            logger.info(f"[{conversation_id}] ⚡ Instant routing: single device → internet_single_device")
            return "internet_single_device"
    
    # ===========================================
    # PRIORITY 2: Context-enriched RAG search
    # ===========================================
    if problem_description:
        # Build enriched query with context
        enriched_query = f"{problem_type} {problem_description}"
        
        # Add scope context
        if problem_context:
            scope = problem_context.get("scope", "")
            if scope:
                enriched_query += f" affected: {scope}"
            
            # Add what customer already tried
            if problem_context.get("tried_restart"):
                enriched_query += " already restarted router"
            
            if problem_context.get("router_lights"):
                enriched_query += f" lights: {problem_context['router_lights']}"
        
        # Add diagnostic context
        if diagnostic_results:
            ip_check = diagnostic_results.get("ip_assignment_check", {})
            if ip_check.get("success"):
                enriched_query += " router has IP"
        
        logger.info(f"[{conversation_id}] 🔍 RAG query: {enriched_query[:80]}...")
        
        # Call RAG with enriched query
        rag_scenario = select_scenario(enriched_query, problem_type, conversation_id)
        if rag_scenario:
            return rag_scenario
    
    # ===========================================
    # PRIORITY 3: Default fallback
    # ===========================================
    defaults = {
        "internet": "internet_no_connection",
        "tv": "tv_no_signal",
        "phone": "internet_no_connection",
        "other": "internet_no_connection",
    }
    
    logger.info(f"[{conversation_id}] 📋 Default fallback: {defaults.get(problem_type)}")
    return defaults.get(problem_type, "internet_no_connection")


def select_scenario(problem_description: str, problem_type: str, conversation_id: str = "") -> str:
    """Select appropriate troubleshooting scenario using RAG."""
    logger.info(f"[{conversation_id}] Selecting scenario for type: {problem_type}")
    
    actual_type = problem_type
    if problem_type == "other" and problem_description:
        desc_lower = problem_description.lower()
        
        if any(kw in desc_lower for kw in ["internet", "wifi", "router", "tinklas"]):
            actual_type = "internet"
        elif any(kw in desc_lower for kw in ["televizor", "tv", "kanal"]):
            actual_type = "tv"
        elif any(kw in desc_lower for kw in ["telefon", "skamb"]):
            actual_type = "phone"
    # Naudoti hybrid retriever
    try:
        retriever = get_hybrid_retriever()
    except Exception:
        # Fallback to base retriever
        retriever = get_retriever()
 
    
    try:
        retriever.load("production")
    except Exception as e:
        logger.error(f"[{conversation_id}] Error loading KB: {e}")
    
    results = retriever.retrieve(
        query=f"{actual_type} {problem_description}",
        top_k=3,
        threshold=0.5,
        filter_metadata={"type": "scenario", "problem_type": actual_type}
    )
    
    if results:
        scenario_id = results[0]["metadata"]["scenario_id"]
        logger.info(f"[{conversation_id}] Selected scenario: {scenario_id}")
        return scenario_id
    
    # default_scenarios = {
    #     "internet": "internet_no_connection",
    #     "tv": "tv_no_signal",
    #     "phone": "internet_no_connection",
    #     "other": "internet_no_connection",
    # }
    # return default_scenarios.get(actual_type, "internet_no_connection")
    return None


def format_step_instruction(step: dict, customer_name: str = "", conversation_id: str = "") -> str:
    """Format step instruction for customer - ONE SUB-TASK AT A TIME."""
    instruction = step.get("instruction", "")
    output_language = get_language_name()
    
    greeting = ""
    if customer_name:
        greeting = f"{customer_name.split()[0]}, "
    
    system_prompt = f"""You are an ISP customer service assistant on a phone call.

IMPORTANT:
- This is a phone call - customer cannot see text
- Give only ONE action at a time
- Ask them to do one thing and report the result

From this instruction, extract only the FIRST action:
{instruction}

Respond briefly - just the first action, one sentence.
CRITICAL: Respond ONLY in {output_language} language."""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "What's the first action?"}
        ]
        first_action = llm_completion(messages, temperature=0.2, max_tokens=150)
        return f"{greeting}{first_action}"
    except Exception as e:
        logger.warning(f"[{conversation_id}] Could not simplify instruction: {e}")
        sentences = instruction.split('. ')
        return f"{greeting}{sentences[0]}."


def analyze_user_response(user_response: str, current_step: dict, conversation_id: str = "") -> StepResponse:
    """Analyze user's response to troubleshooting step."""
    output_language = get_language_name()
    step_instruction = current_step.get("instruction", "")
    branches = current_step.get("branches", {})
    
    # Build branches info for LLM - branches is dict: {branch_id: {condition, next_step, ...}}
    branches_info = ""
    branch_keys = []
    if branches and isinstance(branches, dict):
        branches_info = "Available branches based on user response:\n"
        for branch_id, branch_data in branches.items():
            branch_keys.append(branch_id)
            condition = branch_data.get('condition', '') if isinstance(branch_data, dict) else str(branch_data)
            branches_info += f"- {branch_id}: {condition}\n"
    
    system_prompt = f"""You are analyzing a customer's response during ISP troubleshooting.

Current step: {current_step.get('title', '')}
Instruction given: {step_instruction}

{branches_info}

YOUR TASK:
1. Understand what the customer reported/observed
2. Select the BEST MATCHING branch from the available options
3. Determine if clarification is needed

⚠️ CRITICAL RULES FOR selected_branch:
- You MUST select one of these exact branch IDs: {branch_keys}
- Match the customer's response to the closest branch condition
- Examples:
  - "lemputes žalios" or "all lights green" → select "all_green"
  - "nedega" or "no lights" → select "no_lights"  
  - "tik power dega" → select "power_only"

⚠️ CRITICAL RULES FOR problem_resolved:
- problem_resolved = true ONLY if customer EXPLICITLY says internet/service is NOW WORKING
- Words that mean RESOLVED: "veikia", "jau gerai", "išsisprendė", "works now", "fixed", "prisijungė"
- Words that are NOT resolved (just diagnostic answers): "lemputes žalios", "perkroviau", "patikrinau", "dega", "įjungtas"
- If customer just answers a diagnostic question → problem_resolved = FALSE

Respond in JSON:
{{
    "understood": true/false,
    "user_answer_summary": "brief summary of what customer reported",
    "selected_branch": "one of {branch_keys} or null if unclear",
    "needs_clarification": true/false,
    "clarification_question": "question in {output_language} if clarification needed, else null",
    "needs_next_substep": false,
    "problem_resolved": false
}}

REMEMBER: 
- selected_branch must be EXACTLY one of: {branch_keys}
- problem_resolved is almost always FALSE unless customer says "veikia" or "works"
- clarification_question MUST be in {output_language}"""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_response}
        ]
        
        response = llm_json_completion(messages, temperature=0.2, max_tokens=300)
        return StepResponse(**response)
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Error analyzing response: {e}")
        return StepResponse(
            understood=False,
            user_answer_summary=user_response,
            needs_clarification=True,
            clarification_question=t("errors.repeat_request")
        )


def check_resolution(user_message: str, conversation_id: str = "") -> ResolutionCheck:
    """Check if user is indicating problem is resolved."""
    output_language = get_language_name()
    
    system_prompt = f"""Analyze if the customer is saying their internet/service problem is now resolved.

Look for:
- Explicit confirmation: "veikia", "works", "gerai", "fixed"
- Explicit denial: "neveikia", "still not working", "vis dar"
- Ambiguous responses that need follow-up

Respond in JSON:
{{
    "is_resolved": true/false,
    "confidence": 0.0-1.0,
    "user_says_working": true/false,
    "user_says_not_working": true/false,
    "needs_confirmation": true/false,
    "response_message": "response in {output_language}"
}}

CRITICAL: response_message MUST be in {output_language}."""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = llm_json_completion(messages, temperature=0.2, max_tokens=200)
        return ResolutionCheck(**response)
        
    except Exception as e:
        logger.error(f"[{conversation_id}] Resolution check error: {e}")
        return ResolutionCheck(
            is_resolved=False,
            confidence=0.0,
            user_says_working=False,
            user_says_not_working=False,
            needs_confirmation=True,
            response_message=t("closing.anything_else")
        )


# =============================================================================
# MAIN NODE FUNCTION
# =============================================================================

def troubleshooting_node(state: Any) -> dict:
    """
    Troubleshooting node - guides customer through troubleshooting steps.
    
    Integrates problem_context to skip steps and start from appropriate step.
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    logger.info(f"[{conversation_id}] Troubleshooting node started")
    
    # Check if problem already resolved
    if _get_attr(state, "problem_resolved", False):
        logger.info(f"[{conversation_id}] Problem already resolved - passing through")
        return {"current_node": "troubleshooting"}
    
    # Check if already needs escalation
    if _get_attr(state, "troubleshooting_needs_escalation", False):
        logger.info(f"[{conversation_id}] Already needs escalation - passing through")
        return {"current_node": "troubleshooting"}
    
    ts_state = _get_troubleshooting_state(state)
    problem_description = _get_attr(state, "problem_description", "")
    problem_type = _get_attr(state, "problem_type", "internet")
    problem_context = _get_attr(state, "problem_context", {})
    customer_name = _get_attr(state, "customer_name", "")
    diagnostic_results = _get_attr(state, "diagnostic_results", {})  # Get diagnostic results
    
    # Build context summary for logging
    context_summary = build_context_summary(problem_context, problem_type)
    if context_summary:
        logger.info(f"[{conversation_id}] Context:\n{context_summary}")
    
    # =========================================================================
    # FIRST TIME - Select scenario and determine starting step (SMART ROUTING)
    # =========================================================================
    if not ts_state["scenario_id"]:
        logger.info(f"[{conversation_id}] First time - selecting scenario with smart routing")
        
        # Use smart scenario selection
        # scenario_id = get_smart_scenario_id(problem_type, problem_context, diagnostic_results)
        scenario_id = get_smart_scenario_id(
                                            problem_type=problem_type,
                                            problem_context=problem_context,
                                            problem_description=problem_description,
                                            diagnostic_results=diagnostic_results,
                                            conversation_id=conversation_id
                                        )
        logger.info(f"[{conversation_id}] Selected scenario: {scenario_id}")
        
        scenario_loader = get_scenario_loader()
        scenario = scenario_loader.get_scenario(scenario_id)
        
        # Fallback to default scenario if selected one not found
        if not scenario and scenario_id != "internet_no_connection":
            logger.warning(f"[{conversation_id}] Scenario '{scenario_id}' not found, falling back to 'internet_no_connection'")
            scenario_id = "internet_no_connection"
            scenario = scenario_loader.get_scenario(scenario_id)
        
        if not scenario:
            logger.error(f"[{conversation_id}] Scenario not found: {scenario_id}")
            error_msg = add_message(
                role="assistant",
                content=t("troubleshooting.scenario_not_found"),
                node="troubleshooting"
            )
            return {
                "messages": [error_msg],
                "current_node": "troubleshooting",
                "troubleshooting_needs_escalation": True,
                "troubleshooting_escalation_reason": "scenario_not_found",
            }
        
        # ========================================
        # SMART ROUTING: Determine starting step
        # ========================================
        starting_step, skipped_steps, skip_message = determine_starting_step(
            scenario, 
            problem_context, 
            problem_type, 
            diagnostic_results,
            conversation_id
        )
        
        instruction_text = format_step_instruction(starting_step, customer_name, conversation_id)
        
        # Build intro message
        intro = t("troubleshooting.starting")
        if skip_message:
            intro = f"{intro} {skip_message}"
        
        step_title_raw = starting_step.get('title', '')
        step_title = translate_step_content(step_title_raw, "title", conversation_id)
        
        message = add_message(
            role="assistant",
            content=f"{intro}\n\n**{step_title}**\n\n{instruction_text}",
            node="troubleshooting"
        )
        
        logger.info(f"[{conversation_id}] Started scenario: {scenario_id} | step: {starting_step.get('step_id')} | skipped: {skipped_steps}")
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_scenario_id": scenario_id,
            "troubleshooting_current_step": starting_step.get("step_id"),
            "troubleshooting_completed_steps": [],
            "troubleshooting_skipped_steps": skipped_steps,
        }
    
    # =========================================================================
    # CONTINUING - Analyze user response
    # =========================================================================
    user_response = get_last_user_message(state)
    logger.info(f"[{conversation_id}] Analyzing response: {user_response[:50]}...")
    
    # Check for help request
    if detect_help_request(user_response):
        logger.info(f"[{conversation_id}] Help request detected")
        
        scenario_loader = get_scenario_loader()
        scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
        current_step = scenario.get_step(ts_state["current_step"]) if scenario else {}
        
        help_response = generate_help_response(current_step, conversation_id)
        
        message = add_message(
            role="assistant",
            content=help_response,
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_checked_items": ts_state.get("checked_items", {}),
        }
    
    # Check for frustration
    frustration = detect_frustration(user_response)
    
    if frustration.get("should_escalate"):
        logger.info(f"[{conversation_id}] User wants escalation")
        
        message = add_message(
            role="assistant",
            content=t("troubleshooting.offer_escalation"),
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "customer_requested",
        }
    
    if frustration.get("should_apologize"):
        logger.info(f"[{conversation_id}] Frustration detected | severity={frustration.get('severity')}")
        
        apology_response = generate_apology_response(
            frustration,
            ts_state.get("checked_items", {}),
            problem_description
        )
        
        message = add_message(
            role="assistant",
            content=apology_response,
            node="troubleshooting"
        )
        
        if frustration.get("severity", 0) >= 3:
            return {
                "messages": [message],
                "current_node": "troubleshooting",
                "troubleshooting_needs_escalation": True,
                "troubleshooting_escalation_reason": "customer_frustrated",
            }
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
        }
    
    # Check for resolution indicators
    resolution_phrases = t_list("resolution.positive")
    if any(phrase in user_response.lower() for phrase in resolution_phrases):
        logger.info(f"[{conversation_id}] Possible resolution detected")
        
        resolution = check_resolution(user_response, conversation_id)
        
        if resolution.is_resolved and resolution.confidence > 0.7:
            logger.info(f"[{conversation_id}] Problem RESOLVED!")
            
            message = add_message(
                role="assistant",
                content=t("troubleshooting.resolved"),
                node="troubleshooting"
            )
            
            return {
                "messages": [message],
                "current_node": "troubleshooting",
                "problem_resolved": True,
                "troubleshooting_completed_steps": ts_state["completed_steps"] + [ts_state["current_step"]],
            }
    
    # Analyze response and continue scenario
    scenario_loader = get_scenario_loader()
    scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
    
    if not scenario:
        logger.error(f"[{conversation_id}] Scenario lost: {ts_state['scenario_id']}")
        return {
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "scenario_lost",
        }
    
    current_step = scenario.get_step(ts_state["current_step"])
    
    if not current_step:
        logger.error(f"[{conversation_id}] Step not found: {ts_state['current_step']}")
        error_msg = add_message(
            role="assistant",
            content=t("troubleshooting.step_not_found"),
            node="troubleshooting"
        )
        return {
            "messages": [error_msg],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "step_not_found",
        }
    
    # Analyze user response
    analysis = analyze_user_response(user_response, current_step, conversation_id)
    
    logger.info(
        f"[{conversation_id}] Analysis: understood={analysis.understood}, "
        f"branch={analysis.selected_branch}, resolved={analysis.problem_resolved}"
    )
    
    # Handle resolution from analysis
    if analysis.problem_resolved:
        logger.info(f"[{conversation_id}] Problem resolved (from analysis)")
        
        message = add_message(
            role="assistant",
            content=t("troubleshooting.resolved"),
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "problem_resolved": True,
        }
    
    # Handle clarification needed
    if analysis.needs_clarification:
        message = add_message(
            role="assistant",
            content=analysis.clarification_question or t("errors.repeat_request"),
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
        }
    
    # Get next step based on selected branch
    next_step = None
    branch_message = ""
    
    if analysis.selected_branch:
        branches = current_step.get("branches", {})
        branch_data = branches.get(analysis.selected_branch, {})
        
        if branch_data:
            branch_message = branch_data.get("message", "")
            next_step_id = branch_data.get("next_step")
            action = branch_data.get("action")
            
            # Handle special actions
            if action == "escalate" or next_step_id == "escalate":
                logger.info(f"[{conversation_id}] Branch leads to escalation")
                
                content = branch_message if branch_message else t("troubleshooting.escalating")
                message = add_message(
                    role="assistant",
                    content=content,
                    node="troubleshooting"
                )
                
                return {
                    "messages": [message],
                    "current_node": "troubleshooting",
                    "troubleshooting_needs_escalation": True,
                    "troubleshooting_escalation_reason": branch_data.get("reason", "branch_escalate"),
                }
            
            if action == "resolved" or next_step_id == "resolved":
                logger.info(f"[{conversation_id}] Branch indicates resolved")
                
                content = branch_message if branch_message else t("troubleshooting.resolved")
                message = add_message(
                    role="assistant",
                    content=content,
                    node="troubleshooting"
                )
                
                return {
                    "messages": [message],
                    "current_node": "troubleshooting",
                    "problem_resolved": True,
                }
            
            # Get next step by ID
            if next_step_id:
                next_step = scenario.get_step(next_step_id)
    
    # Fallback: try to get next sequential step if no branch selected
    if not next_step:
        current_step_id = ts_state["current_step"]
        if isinstance(current_step_id, int):
            next_step = scenario.get_step(current_step_id + 1)
    
    if not next_step:
        logger.info(f"[{conversation_id}] No more steps - escalating")
        
        message = add_message(
            role="assistant",
            content=t("troubleshooting.escalating"),
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "no_more_steps",
            "troubleshooting_completed_steps": ts_state["completed_steps"] + [ts_state["current_step"]],
        }
    
    # Show next step
    instruction_text = format_step_instruction(next_step, customer_name, conversation_id)
 
    step_title_raw = next_step.get('title', '')
    step_title = translate_step_content(step_title_raw, "title", conversation_id)
    
    message = add_message(
        role="assistant",
        content=f"**{step_title}**\n\n{instruction_text}",
        node="troubleshooting"
    )
    
    logger.info(f"[{conversation_id}] Moving to step: {next_step.get('step_id')} | lang={get_language()}")
    
    return {
        "messages": [message],
        "current_node": "troubleshooting",
        "troubleshooting_current_step": next_step.get("step_id"),
        "troubleshooting_completed_steps": ts_state["completed_steps"] + [ts_state["current_step"]],
    }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================

def troubleshooting_router(state: Any) -> str:
    """
    Route after troubleshooting.
    
    Returns:
        - "create_ticket" → needs escalation or problem resolved (for logging)
        - "closing" → problem resolved, ready to close
        - "end" → waiting for user input
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    
    problem_resolved = _get_attr(state, "problem_resolved", False)
    needs_escalation = _get_attr(state, "troubleshooting_needs_escalation", False)
    
    if needs_escalation:
        reason = _get_attr(state, "troubleshooting_escalation_reason", "unknown")
        logger.info(f"[{conversation_id}] Router → create_ticket (escalation: {reason})")
        return "create_ticket"
    
    if problem_resolved:
        logger.info(f"[{conversation_id}] Router → closing (resolved)")
        return "closing"
    
    logger.info(f"[{conversation_id}] Router → end (waiting for user)")
    return "end"
