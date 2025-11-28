"""
Troubleshooting Node v2 - Guided customer troubleshooting with scenarios

Integrates with problem_context to:
1. Skip steps customer already tried
2. Start from appropriate step based on known info
3. Inform LLM about prior context
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

from src.rag.scenario_loader import get_scenario_loader
from src.rag.retriever import get_retriever

from src.services.llm import llm_json_completion
from src.services.config_loader import load_config
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = get_logger(__name__)


# =============================================================================
# HELP REQUEST DETECTION
# =============================================================================

def detect_help_request(user_message: str) -> bool:
    """
    Detect if user is asking for help with current instruction.
    
    Args:
        user_message: User's message
        
    Returns:
        True if user needs help/explanation
    """
    help_phrases = [
        # Lithuanian
        "kaip tai padaryti",
        "kaip tai",
        "kaip?",
        "nežinau kaip",
        "nezinau kaip",
        "padėk",
        "padek",
        "paaiškink",
        "paaiskink",
        "nemoku",
        "nesuprantu",
        "kur rasti",
        "kur yra",
        "kas tai",
        "ką reiškia",
        "ka reiskia",
        "kur tai",
        "kaip surasti",
        "kaip rasti",
        "kaip patikrinti",
        "neįmanoma",
        "neimanoma",
        "per sunku",
        "nesigauna",
        # English fallback
        "how to",
        "how do i",
        "what is",
        "where is",
        "help me",
    ]
    
    msg_lower = user_message.lower().strip()
    
    # Direct match
    if any(phrase in msg_lower for phrase in help_phrases):
        return True
    
    # Short confused responses
    if msg_lower in ["?", "??", "kas", "kur", "kaip", "ką", "ka"]:
        return True
    
    return False


def generate_help_response(current_step: dict, help_topic: str = None) -> str:
    """
    Generate detailed help instructions for current troubleshooting step.
    
    Args:
        current_step: Current step dict with title and instruction
        help_topic: Specific topic user asked about (optional)
        
    Returns:
        Detailed help message in Lithuanian
    """
    step_title = current_step.get("title", "").lower()
    step_instruction = current_step.get("instruction", "")
    
    # WiFi check help
    if "wifi" in step_title or "wifi" in step_instruction.lower():
        return """Suprantu, padėsiu! Štai kaip patikrinti WiFi telefone:

**Android telefone:**
1. Atidarykite "Nustatymai" (Settings) - dažniausiai krumpliaračio ikona
2. Paspauskite "WiFi" arba "Tinklas ir internetas"
3. Patikrinkite ar WiFi jungiklis ĮJUNGTAS (turi būti žalias/mėlynas)
4. Jei įjungtas - ar matote savo namų tinklo pavadinimą?

**iPhone telefone:**
1. Atidarykite "Settings" (Nustatymai)
2. Paspauskite "Wi-Fi"
3. Patikrinkite ar jungiklis žalias (įjungtas)
4. Ar matote savo tinklo pavadinimą su varnele?

Pasakykite man, ar WiFi įjungtas ir ar matote savo tinklą sąraše?"""

    # Router lights help
    if "lemput" in step_title or "lemput" in step_instruction.lower() or "šviesos" in step_instruction.lower():
        return """Suprantu, padėsiu! Routerio lempučių tikrinimas:

**Kur rasti routerį:**
- Paprastai stovi prie kompiuterio arba prie telefono lizdo
- Tai dėžutė su keliomis šviečiančiomis lempučių

**Ką tikrinti:**
1. **POWER** lempute - ar dega? (rodo kad routeris įjungtas)
2. **INTERNET** arba **WAN** lempute - ar dega? (rodo interneto ryšį)
3. **WiFi** lempute - ar dega? (rodo belaidį tinklą)

Jei visos lemputes dega žaliai - routeris veikia gerai.
Jei kuri nors nedega arba mirksi raudonai - gali būti problema.

Pasakykite, kokios spalvos dega lemputes?"""

    # Router restart help
    if "perkrau" in step_title or "perkrau" in step_instruction.lower() or "restart" in step_instruction.lower():
        return """Suprantu, padėsiu perkrauti routerį:

**Kaip perkrauti:**
1. Raskite routerio maitinimo laidą (juodas laidas einantis į rozetę)
2. Ištraukite laidą iš rozetės
3. Palaukite 30 sekundžių
4. Įjunkite laidą atgal į rozetę
5. Palaukite 2-3 minutes kol routeris pilnai įsijungs

**Kaip žinoti kad įsijungė:**
- Lemputes nustos mirksėti ir degs stabiliai
- Tai užtrunka apie 2-3 minutes

Ar pavyko perkrauti? Pasakykite kai lemputes nustos mirksėti."""

    # Cable check help
    if "kabel" in step_title or "kabel" in step_instruction.lower() or "laid" in step_instruction.lower():
        return """Suprantu, padėsiu patikrinti kabelius:

**Kokie kabeliai:**
1. **Maitinimo laidas** - juodas, eina į rozetę
2. **Interneto laidas** - dažniausiai geltonas arba pilkas, eina į sieną arba modemą
3. **LAN kabelis** - jei kompiuteris prijungtas laidu

**Ką tikrinti:**
- Ar visi kabeliai tvirtai įkišti?
- Ar nėra pažeistų/perlenktų vietų?
- Pabandykite ištraukti ir vėl įkišti kiekvieną kabelį

Ar visi kabeliai tvirtai prijungti?"""

    # Generic help
    return f"""Suprantu, kad reikia daugiau paaiškinimo.

Dabartinis žingsnis: {current_step.get('title', 'Troubleshooting')}

{step_instruction}

Jei kažkas neaišku - pasakykite konkrečiai kas, ir pabandysiu paaiškinti paprasčiau."""


# =============================================================================
# FRUSTRATION DETECTION
# =============================================================================

def detect_frustration(user_message: str) -> dict:
    """
    Detect if user is frustrated, annoyed, or pointing out bot mistakes.
    
    Args:
        user_message: User's message
        
    Returns:
        Dict with frustration analysis
    """
    msg_lower = user_message.lower().strip()
    
    # Frustration phrases - user is annoyed
    frustration_phrases = [
        "negali padėti", "negali padeti",
        "nepadedi", "nepadeda",
        "nenaudingas", "nenaudinga",
        "blogas", "bloga",
        "neveikia", "neveikia šitas",
        "kvailas", "kvaila",
        "beprasmis", "beprasme",
        "gaila laiko",
        "nesąmonė", "nesamone",
        "atsibodo",
        "pakaks", "gana",
        "užtenka", "uztenka",
    ]
    
    # Repetition complaints - user says we're repeating
    repetition_phrases = [
        "jau sakiau",
        "jau minėjau", "jau minejau",
        "jau atsakiau",
        "kartoji", "kartojat",
        "vėl tas pats", "vel tas pats",
        "tą patį", "ta pati",
        "neatsimeni",
        "pamiršai", "pamirso",
        "kiek kartų", "kiek kartu",
        "trečią kartą", "trecia karta",
        "antrą kartą", "antra karta",
    ]
    
    # Escalation requests - user wants human
    escalation_phrases = [
        "noriu žmogaus", "noriu zmogaus",
        "noriu operatorius",
        "noriu kalbėti su",
        "sujunkite su",
        "perduokite",
        "tikrą žmogų", "tikra zmogu",
        "gyvą žmogų", "gyva zmogu",
        "vadovą", "vadova",
        "techniką", "technika",
    ]
    
    is_frustrated = any(phrase in msg_lower for phrase in frustration_phrases)
    is_repetition_complaint = any(phrase in msg_lower for phrase in repetition_phrases)
    wants_escalation = any(phrase in msg_lower for phrase in escalation_phrases)
    
    # Determine severity
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
        "severity": severity,  # 0=none, 1=mild, 2=moderate, 3+=severe
        "should_apologize": is_frustrated or is_repetition_complaint,
        "should_summarize": is_repetition_complaint,
        "should_escalate": wants_escalation or severity >= 4,
    }


def generate_apology_response(frustration: dict, checked_items: dict, problem_description: str) -> str:
    """
    Generate appropriate apology response based on frustration type.
    
    Args:
        frustration: Frustration analysis dict
        checked_items: What we've already checked
        problem_description: Original problem
        
    Returns:
        Apology message
    """
    # Build summary of what we know
    summary_parts = []
    if checked_items:
        if "router_lights" in checked_items:
            summary_parts.append(f"routerio lemputes: {checked_items['router_lights']}")
        if checked_items.get("router_restarted"):
            summary_parts.append("routeris perkrautas")
        if "wifi_status" in checked_items:
            summary_parts.append(f"WiFi: {checked_items['wifi_status']}")
        if "device_wifi" in checked_items:
            summary_parts.append(f"įrenginio WiFi: {checked_items['device_wifi']}")
    
    summary = ", ".join(summary_parts) if summary_parts else "turite interneto problemą"
    
    # Repetition complaint response
    if frustration.get("is_repetition_complaint"):
        return f"""Labai atsiprašau, kad kartoju klausimus! Turite visišką teisę pykti.

Apibendrinu ką jau žinome:
• Problema: {problem_description}
• Jau patikrinta: {summary}

Pabandykime kitaip - ar galite pasakyti, ar dabar telefone matote WiFi tinklo pavadinimą ir ar prie jo prisijungęs?"""

    # General frustration response
    if frustration.get("is_frustrated"):
        return f"""Atsiprašau, kad nepavyksta greitai išspręsti problemos. Suprantu jūsų nusivylimą.

Ką žinome: {summary}

Ar norėtumėte, kad sukurčiau užklausą technikui? Jis galėtų paskambinti ir padėti išsamiau."""

    # Escalation request response
    if frustration.get("wants_escalation"):
        return """Suprantu, sukursiu užklausą ir mūsų specialistas su jumis susisieks artimiausiu metu.

Ar yra konkretus laikas, kada būtų patogiau sulaukti skambučio?"""

    # Default
    return "Atsiprašau už nepatogumus. Pabandykime dar kartą."


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
    needs_next_substep: bool = False
    next_substep_instruction: str | None = None
    # NEW: Track what was checked in this response
    extracted_checks: dict = {}  # {"router_lights": "žalios", "router_restarted": true}


# =============================================================================
# CONTEXT INTEGRATION FUNCTIONS
# =============================================================================

def get_troubleshooting_mappings() -> dict:
    """Load troubleshooting mappings config."""
    try:
        return load_config("troubleshooting_mappings")
    except FileNotFoundError:
        logger.warning("troubleshooting_mappings.yaml not found, using defaults")
        return {}


def build_context_summary(problem_context: dict, problem_type: str) -> str:
    """
    Build human-readable summary of what we know from problem_context.
    
    Args:
        problem_context: Dict with extracted facts from problem capture
        problem_type: internet/tv/phone
        
    Returns:
        Summary string for LLM context
    """
    if not problem_context:
        return ""
    
    summary_parts = []
    
    # Duration
    duration = problem_context.get("duration")
    if duration:
        summary_parts.append(f"Problema prasidėjo: {duration}")
    
    # Scope
    scope = problem_context.get("scope")
    if scope:
        if scope in ["visi", "visur", "visuose", "all_devices"]:
            summary_parts.append("Problema visuose įrenginiuose")
        else:
            summary_parts.append(f"Paveikti įrenginiai: {scope}")
    
    # Restart attempt
    tried_restart = problem_context.get("tried_restart")
    if tried_restart is True:
        summary_parts.append("Klientas JAU BANDĖ perkrauti routerį - NEKLAUSK dar kartą!")
    elif tried_restart is False:
        summary_parts.append("Klientas DAR NEBANDĖ perkrauti routerio")
    
    # Router lights
    router_lights = problem_context.get("router_lights")
    if router_lights:
        if router_lights in ["nedega", "off", "nėra"]:
            summary_parts.append("Routerio lemputos NEDEGA - tikėtina maitinimo problema")
        elif router_lights in ["dega", "on", "žalia", "green"]:
            summary_parts.append("Routerio lemputos dega")
        else:
            summary_parts.append(f"Routerio lemputos: {router_lights}")
    
    # WiFi visibility
    wifi_visible = problem_context.get("wifi_visible")
    if wifi_visible is True:
        summary_parts.append("Klientas mato WiFi tinklą")
    elif wifi_visible is False:
        summary_parts.append("Klientas NEMATO WiFi tinklo")
    
    # TV specific
    decoder_status = problem_context.get("decoder_status")
    if decoder_status:
        summary_parts.append(f"Dekoderio būklė: {decoder_status}")
    
    has_image = problem_context.get("has_image")
    if has_image is False:
        summary_parts.append("Nėra vaizdo ekrane")
    
    has_sound = problem_context.get("has_sound")
    if has_sound is False:
        summary_parts.append("Nėra garso")
    
    if not summary_parts:
        return ""
    
    return "ŽINOMA INFORMACIJA IŠ ANKSTESNIO POKALBIO:\n- " + "\n- ".join(summary_parts)


def build_checked_items_summary(checked_items: dict) -> str:
    """
    Build summary of items already checked during troubleshooting.
    This is CRITICAL to prevent repeating questions.
    
    Args:
        checked_items: Dict of items already checked
        
    Returns:
        Summary string for LLM - emphatic about not repeating
    """
    if not checked_items:
        return ""
    
    summary_parts = []
    
    # Router lights
    if "router_lights" in checked_items:
        value = checked_items["router_lights"]
        summary_parts.append(f"🔴 LEMPUTES JAU PATIKRINTOS: {value}")
    
    # Router restart
    if checked_items.get("router_restarted"):
        summary_parts.append("🔴 ROUTERIS JAU PERKRAUTAS")
    
    # WiFi check
    if "wifi_status" in checked_items:
        value = checked_items["wifi_status"]
        summary_parts.append(f"🔴 WIFI JAU PATIKRINTAS: {value}")
    
    # Device WiFi
    if "device_wifi" in checked_items:
        value = checked_items["device_wifi"]
        summary_parts.append(f"🔴 ĮRENGINIO WIFI: {value}")
    
    # Power check
    if "power_checked" in checked_items:
        summary_parts.append("🔴 MAITINIMAS JAU PATIKRINTAS")
    
    # Cable check
    if "cables_checked" in checked_items:
        summary_parts.append("🔴 KABELIAI JAU PATIKRINTI")
    
    # Any other items
    standard_keys = {"router_lights", "router_restarted", "wifi_status", "device_wifi", "power_checked", "cables_checked"}
    for key, value in checked_items.items():
        if key not in standard_keys:
            summary_parts.append(f"🔴 {key.upper()}: {value}")
    
    if not summary_parts:
        return ""
    
    return """
⚠️⚠️⚠️ KRITIŠKAI SVARBU - JAU PATIKRINTA (NIEKADA NEKARTOTI!): ⚠️⚠️⚠️
""" + "\n".join(summary_parts) + """

JEIGU KLAUSI APIE KAŽKĄ KAS JAU PATIKRINTA - TAI KLAIDA!
"""


def determine_starting_step(scenario, problem_context: dict, problem_type: str, diagnostic_results: dict = None) -> dict:
    """
    Determine which step to start from based on problem_context AND diagnostic_results.
    
    Args:
        scenario: Loaded scenario object
        problem_context: Dict with extracted facts from problem capture
        problem_type: internet/tv/phone
        diagnostic_results: Results from diagnostics node (port status, IP assignment, etc.)
        
    Returns:
        Step dict to start from (may skip initial steps)
    """
    
    # ===========================================
    # PRIORITY 1: Check diagnostic_results first
    # ===========================================
    if diagnostic_results:
        ip_check = diagnostic_results.get("ip_assignment_check", {})
        port_check = diagnostic_results.get("port_status_check", {})
        
        # Router confirmed working if:
        # - IP is assigned and active
        # - Port is up
        ip_active = ip_check.get("success") and ip_check.get("active_count", 0) > 0
        port_healthy = port_check.get("diagnostics", {}).get("all_ports_healthy", False)
        
        router_confirmed_working = ip_active and port_healthy
        
        if router_confirmed_working:
            logger.info("✅ Diagnostics confirm router is working - skipping router checks")
            logger.info(f"   IP active: {ip_active}, Port healthy: {port_healthy}")
            
            # Try to find device check step
            device_step = scenario.get_step("step_4") or scenario.get_step("device_check")
            if device_step:
                logger.info(f"   → Starting from step: {device_step.get('step_id', 'device_check')}")
                return device_step
    
    # ===========================================
    # PRIORITY 2: Check scope (single device)
    # ===========================================
    if problem_context:
        scope = str(problem_context.get("scope", "")).lower()
        single_device_keywords = ["telefonas", "phone", "kompiuteris", "laptop", "vienas", "tik vienas"]
        
        is_single_device = any(kw in scope for kw in single_device_keywords)
        
        if is_single_device:
            logger.info(f"✅ Single device affected: '{scope}' - skipping router checks")
            device_step = scenario.get_step("step_4") or scenario.get_step("device_check")
            if device_step:
                return device_step
    
    # ===========================================
    # PRIORITY 3: Check problem_context facts
    # ===========================================
    if not problem_context:
        return scenario.get_first_step()
    
    mappings = get_troubleshooting_mappings()
    rules = mappings.get("context_to_skip_rules", {}).get(problem_type, [])
    step_aliases = mappings.get("step_aliases", {})
    
    # Find matching rule
    best_match = None
    best_match_score = 0
    
    for rule in rules:
        condition = rule.get("condition", {})
        match_score = 0
        all_conditions_met = True
        
        for field, expected_value in condition.items():
            actual_value = problem_context.get(field)
            
            if actual_value is None:
                all_conditions_met = False
                break
            
            if isinstance(expected_value, bool):
                if actual_value == expected_value:
                    match_score += 1
                else:
                    all_conditions_met = False
                    break
            elif isinstance(expected_value, str):
                actual_str = str(actual_value).lower()
                expected_str = expected_value.lower()
                if expected_str in actual_str or actual_str in expected_str:
                    match_score += 1
                elif expected_str == "dega" and any(x in actual_str for x in ["dega", "žalia", "green", "on", "šviečia"]):
                    match_score += 1
                elif expected_str == "nedega" and any(x in actual_str for x in ["nedega", "off", "nėra", "tamsu"]):
                    match_score += 1
                else:
                    all_conditions_met = False
                    break
        
        if all_conditions_met and match_score > best_match_score:
            best_match = rule
            best_match_score = match_score
    
    if best_match:
        start_from = best_match.get("start_from")
        reason = best_match.get("reason", "")
        skip_steps = best_match.get("skip_steps", [])
        
        logger.info(f"Context match: {reason}")
        logger.info(f"Skipping steps: {skip_steps}, starting from: {start_from}")
        
        if start_from:
            scenario_id = scenario.scenario_id if hasattr(scenario, 'scenario_id') else ""
            aliases = step_aliases.get(scenario_id, {})
            actual_step_id = aliases.get(start_from, start_from)
            
            step = scenario.get_step(actual_step_id)
            if step:
                return step
            
            try:
                step_num = int(start_from.replace("step_", ""))
                step = scenario.get_step(f"step_{step_num}")
                if step:
                    return step
            except (ValueError, AttributeError):
                pass
    
    # Default: start from first step
    return scenario.get_first_step()


def get_skipped_steps_message(problem_context: dict, problem_type: str) -> str:
    """
    Generate message explaining why we're skipping steps.
    
    Args:
        problem_context: Dict with extracted facts
        problem_type: internet/tv/phone
        
    Returns:
        Message string or empty
    """
    parts = []
    
    tried_restart = problem_context.get("tried_restart")
    router_lights = problem_context.get("router_lights")
    
    if tried_restart is True:
        parts.append("jau bandėte perkrauti routerį")
    
    if router_lights:
        lights_str = str(router_lights).lower()
        if any(x in lights_str for x in ["nedega", "off", "nėra"]):
            parts.append("lemputes nedega")
        elif any(x in lights_str for x in ["dega", "on", "žalia"]):
            parts.append("lemputes dega")
    
    if parts:
        return f"Kadangi {', '.join(parts)}, praleisime kai kuriuos žingsnius."
    
    return ""


# =============================================================================
# HELPER FUNCTIONS (existing)
# =============================================================================

def _get_troubleshooting_state(state) -> dict:
    """Get troubleshooting state from conversation state."""
    scenario_id = _get_attr(state, "troubleshooting_scenario_id")
    current_step = _get_attr(state, "troubleshooting_current_step")
    completed_steps = _get_attr(state, "troubleshooting_completed_steps")
    skipped_steps = _get_attr(state, "troubleshooting_skipped_steps")
    checked_items = _get_attr(state, "troubleshooting_checked_items")
    
    return {
        "scenario_id": scenario_id,
        "current_step": current_step if current_step else 1,
        "completed_steps": completed_steps if completed_steps else [],
        "skipped_steps": skipped_steps if skipped_steps else [],
        "checked_items": checked_items if checked_items else {},
    }


def select_scenario(problem_description: str, problem_type: str) -> str:
    """
    Select appropriate troubleshooting scenario using RAG.
    Includes smart fallback if problem_type is 'other'.
    """
    logger.info(f"Selecting scenario for: {problem_description} (type: {problem_type})")
    
    # Smart fallback: if "other" but description suggests specific type
    actual_type = problem_type
    if problem_type == "other" and problem_description:
        desc_lower = problem_description.lower()
        
        # Check for internet-related keywords
        internet_keywords = ["internet", "internetas", "naršyklė", "narsykle", "wifi", 
                           "prisijung", "ryšys", "rysys", "tinklas", "router", "maršrutizator"]
        if any(kw in desc_lower for kw in internet_keywords):
            actual_type = "internet"
            logger.info(f"Smart fallback: 'other' → 'internet' (detected from description)")
        
        # Check for TV-related keywords
        tv_keywords = ["televizor", "tv", "kanal", "dekoder", "vaizdas", "ekran"]
        if any(kw in desc_lower for kw in tv_keywords):
            actual_type = "tv"
            logger.info(f"Smart fallback: 'other' → 'tv' (detected from description)")
        
        # Check for phone-related keywords
        phone_keywords = ["telefon", "skamb", "linija", "ragelis"]
        if any(kw in desc_lower for kw in phone_keywords):
            actual_type = "phone"
            logger.info(f"Smart fallback: 'other' → 'phone' (detected from description)")
    
    retriever = get_retriever()
    
    try:
        success = retriever.load("production")
        if success:
            logger.info("Loaded production knowledge base")
    except Exception as e:
        logger.error(f"Error loading production KB: {e}")
    
    query = f"{actual_type} {problem_description}"
    results = retriever.retrieve(
        query=query,
        top_k=3,
        threshold=0.5,
        filter_metadata={"type": "scenario", "problem_type": actual_type}
    )
    
    if results:
        best_match = results[0]
        scenario_id = best_match["metadata"]["scenario_id"]
        logger.info(f"Selected scenario: {scenario_id} (score: {best_match['score']:.3f})")
        return scenario_id
    
    # Fallback to default based on actual_type (not original problem_type)
    logger.warning(f"No scenario found for {actual_type}, using default")
    
    # Map to existing scenarios
    default_scenarios = {
        "internet": "internet_no_connection",
        "tv": "tv_no_signal",
        "phone": "internet_no_connection",  # Fallback if no phone scenario
        "billing": "internet_no_connection",  # Fallback
        "other": "internet_no_connection",  # Ultimate fallback
    }
    
    return default_scenarios.get(actual_type, "internet_no_connection")


def format_step_instruction(step: dict, customer_name: str = "", is_first_time: bool = True) -> str:
    """
    Format step instruction for customer - ONE SUB-TASK AT A TIME.
    """
    title = step.get("title", "")
    instruction = step.get("instruction", "")
    
    if customer_name:
        first_name = customer_name.split()[0]
        greeting = f"{first_name}, "
    else:
        greeting = ""
    
    if not is_first_time:
        return instruction
    
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
        sentences = instruction.split('. ')
        first_part = '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else instruction
        return f"{greeting}{first_part}"


def analyze_user_response(step: dict, user_response: str, recent_messages: list = None, context_summary: str = "", checked_items: dict = None) -> StepResponse:
    """
    Use LLM to analyze user's response and guide step-by-step.
    Now includes context_summary from problem_context AND checked_items tracking.
    """
    branches = step.get("branches", {})
    instruction = step.get("instruction", "")
    title = step.get("title", "")
    
    conversation_context = ""
    if recent_messages:
        conversation_context = "ANKSTESNĖ POKALBIO DALIS (šiame žingsnyje):\n"
        for msg in recent_messages[-10:]:
            role = "Agentas" if msg.get("role") == "assistant" else "Klientas"
            conversation_context += f"{role}: {msg.get('content', '')}\n"
        conversation_context += "\n---\n"
    
    # Add problem_context info
    prior_knowledge = ""
    if context_summary:
        prior_knowledge = f"""
{context_summary}

SVARBU: Naudok šią informaciją! Jei klientas JAU kažką bandė - neklausinėk to paties!
---
"""
    
    # Add checked items - CRITICAL for not repeating
    checked_items_section = ""
    if checked_items:
        checked_items_section = build_checked_items_summary(checked_items)
    
    system_prompt = f"""Tu esi ISP klientų aptarnavimo asistentas TELEFONO pokalbyje.

{prior_knowledge}
{checked_items_section}

KONTEKSTAS:
- Tai telefoninis pokalbis - klientas NEGALI matyti ankstesnių žinučių
- Vesk klientą PO VIENĄ veiksmą - vienas veiksmas, vienas atsakymas
- Būk kantrus, aiškus, draugiškas
- ⚠️ KRITIŠKAI SVARBU: Atsimink ką klientas JAU patikrino ir NIEKADA NEKARTOK tų pačių klausimų!
- Jei "JAU PATIKRINTA" sekcijoje yra "LEMPUTES" - NEKLAUSTI apie lemputes!
- Jei "JAU PATIKRINTA" sekcijoje yra "PERKRAUTAS" - NEPRAŠYTI perkrauti!

{conversation_context}

DABARTINIS ŽINGSNIS: {title}

PILNA INSTRUKCIJA (ką reikia patikrinti šiame žingsnyje):
{instruction}

GALIMI REZULTATAI kai žingsnis BAIGTAS:
{chr(10).join([f"- {branch_id}: {branch_data.get('condition')}" for branch_id, branch_data in branches.items()])}

DABAR KLIENTAS ATSAKĖ: "{user_response}"

TAVO UŽDUOTIS:
1. Peržiūrėk "JAU PATIKRINTA" sekciją - ŠIŲ DALYKŲ NEKARTOTI!
2. Peržiūrėk pokalbio istoriją - kas dar patikrinta?
3. Ištrauk naują informaciją iš kliento atsakymo į "extracted_checks"
4. Jei reikia daugiau info - klausk TIK to, kas DAR NEPATIKRINTA
5. Jei viskas patikrinta - pasirink tinkamą branch

Atsakyk JSON formatu:
{{
    "understood": true,
    "user_answer_summary": "trumpai ką klientas pasakė/padarė",
    "selected_branch": "branch_id JEI žingsnis baigtas, ARBA null",
    "needs_clarification": false,
    "clarification_question": null,
    "needs_next_substep": true/false,
    "next_substep_instruction": "JEI reikia dar vieno veiksmo - trumpa instrukcija, ARBA null",
    "extracted_checks": {{
        "router_lights": "žalios/raudonos/nedega JEI klientas pasakė",
        "router_restarted": true JEI klientas perkrovė,
        "wifi_status": "įjungtas/išjungtas JEI klientas pasakė",
        "device_wifi": "prisijungęs/neprisijungęs JEI klientas pasakė"
    }}
}}

PAVYZDYS - jei klientas sako "lemputes dega žaliai":
{{
    "understood": true,
    "user_answer_summary": "Visos lemputes dega žaliai",
    "extracted_checks": {{"router_lights": "visos žalios"}},
    ...
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_response}
    ]
    
    try:
        response = llm_json_completion(messages, temperature=0.3, max_tokens=500)
        return StepResponse(**response)
    except Exception as e:
        logger.error(f"Error analyzing response: {e}")
        return StepResponse(
            understood=False,
            user_answer_summary=user_response,
            needs_clarification=True,
            clarification_question="Atsiprašau, ar galėtumėte pakartoti ką matote?"
        )


# =============================================================================
# MAIN NODE FUNCTION
# =============================================================================

def troubleshooting_node(state) -> dict:
    """
    Troubleshooting node v2 - guides customer through troubleshooting steps.
    
    Now integrates problem_context to:
    - Skip steps customer already tried
    - Start from appropriate step
    - Inform LLM about prior context
    """
    logger.info("=== Troubleshooting Node v2 ===")
    
    # Check if problem already resolved - skip processing
    if _get_attr(state, "problem_resolved", False):
        logger.info("Problem already resolved - passing through to router")
        return {"current_node": "troubleshooting"}
    
    # Check if already needs escalation - skip processing
    if _get_attr(state, "troubleshooting_needs_escalation", False):
        logger.info("Already needs escalation - passing through to router")
        return {"current_node": "troubleshooting"}
    
    ts_state = _get_troubleshooting_state(state)
    problem_description = _get_attr(state, "problem_description", "")
    problem_type = _get_attr(state, "problem_type", "internet")
    problem_context = _get_attr(state, "problem_context", {})
    diagnostic_results = _get_attr(state, "diagnostic_results", {})  # ← NEW
    customer_name = _get_attr(state, "customer_name", "")
    
    # Build context summary for LLM
    context_summary = build_context_summary(problem_context, problem_type)
    if context_summary:
        logger.info(f"Context summary:\n{context_summary}")
    
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
        
        # ========================================
        # NEW: Determine starting step based on context AND diagnostics
        # ========================================
        starting_step = determine_starting_step(scenario, problem_context, problem_type, diagnostic_results)
        first_step = scenario.get_first_step()
        
        skipped_steps = []
        skip_message = ""
        
        # Check if we're skipping steps
        if starting_step.get("step_id") != first_step.get("step_id"):
            logger.info(f"Skipping to step: {starting_step.get('step_id')} (was: {first_step.get('step_id')})")
            
            # Collect skipped step IDs
            # (simplified - in real impl would walk through scenario)
            skip_message = get_skipped_steps_message(problem_context, problem_type)
            
            # Mark steps as skipped
            try:
                first_step_num = int(first_step.get("step_id", "step_1").replace("step_", ""))
                start_step_num = int(starting_step.get("step_id", "step_1").replace("step_", ""))
                skipped_steps = [f"step_{i}" for i in range(first_step_num, start_step_num)]
            except ValueError:
                pass
        
        # Format instruction
        instruction_text = format_step_instruction(starting_step, customer_name)
        
        # Build message
        intro = "Gerai, pabandykime išspręsti problemą kartu."
        if skip_message:
            intro = f"Gerai, pabandykime išspręsti problemą. {skip_message}"
        
        message = add_message(
            role="assistant",
            content=f"{intro}\n\n**{starting_step.get('title')}**\n\n{instruction_text}",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_scenario_id": scenario_id,
            "troubleshooting_current_step": starting_step.get("step_id"),
            "troubleshooting_completed_steps": [],
            "troubleshooting_skipped_steps": skipped_steps,
        }
    
    # Get user response
    user_response = get_last_user_message(state)
    logger.info(f"Analyzing user response: {user_response}")
    
    # ===========================================
    # CHECK FOR HELP REQUEST FIRST
    # ===========================================
    if detect_help_request(user_response):
        logger.info("🆘 Help request detected - generating help response")
        
        # Load current step for context
        scenario_loader = get_scenario_loader()
        scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
        current_step = scenario.get_step(ts_state["current_step"]) if scenario else {}
        
        help_response = generate_help_response(current_step, user_response)
        
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
    
    # ===========================================
    # CHECK FOR FRUSTRATION
    # ===========================================
    frustration = detect_frustration(user_response)
    
    if frustration.get("should_escalate"):
        logger.info("😤 User wants escalation - creating ticket")
        
        message = add_message(
            role="assistant",
            content="Suprantu, sukursiu užklausą ir mūsų specialistas su jumis susisieks artimiausiu metu. Atsiprašau už nepatogumus.",
            node="troubleshooting"
        )
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_needs_escalation": True,
            "troubleshooting_escalation_reason": "customer_requested",
            "troubleshooting_checked_items": ts_state.get("checked_items", {}),
        }
    
    if frustration.get("should_apologize"):
        logger.info(f"😤 Frustration detected: {frustration}")
        
        problem_description = _get_attr(state, "problem_description", "interneto problema")
        checked_items = ts_state.get("checked_items", {})
        
        apology_response = generate_apology_response(frustration, checked_items, problem_description)
        
        message = add_message(
            role="assistant",
            content=apology_response,
            node="troubleshooting"
        )
        
        # If severity is high, consider escalation
        if frustration.get("severity", 0) >= 3:
            return {
                "messages": [message],
                "current_node": "troubleshooting",
                "troubleshooting_needs_escalation": True,
                "troubleshooting_escalation_reason": "customer_frustrated",
                "troubleshooting_checked_items": checked_items,
            }
        
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_checked_items": checked_items,
        }

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
    
    # Get already checked items
    checked_items = ts_state.get("checked_items", {})
    logger.info(f"Already checked items: {checked_items}")
    
    # Analyze response with conversation context, problem_context, AND checked_items
    analysis = analyze_user_response(
        current_step, 
        user_response, 
        recent_ts_messages,
        context_summary,
        checked_items  # Pass checked items to prevent repeating
    )
    
    # Merge newly extracted checks into checked_items
    if analysis.extracted_checks:
        checked_items = {**checked_items, **analysis.extracted_checks}
        logger.info(f"Updated checked items: {checked_items}")
    
    logger.info(f"Analysis: branch={analysis.selected_branch}, needs_substep={analysis.needs_next_substep}, clarify={analysis.needs_clarification}")
    
    if analysis.needs_clarification:
        message = add_message(
            role="assistant",
            content=analysis.clarification_question,
            node="troubleshooting"
        )
        return {
            "messages": [message],
            "current_node": "troubleshooting",
            "troubleshooting_checked_items": checked_items,
        }
    
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
            "troubleshooting_checked_items": checked_items,
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
            "troubleshooting_checked_items": checked_items,
        }
    
    elif action == "escalate":
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
            "troubleshooting_checked_items": checked_items,
        }
    
    elif next_step_id:
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
                "troubleshooting_checked_items": checked_items,
            }
        
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
            "troubleshooting_checked_items": checked_items,
        }
    
    else:
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
            "troubleshooting_checked_items": checked_items,
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================

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
