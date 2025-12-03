# """
# Troubleshooting Node v2 - Guided customer troubleshooting with scenarios

# Integrates with problem_context to:
# 1. Skip steps customer already tried
# 2. Start from appropriate step based on known info
# 3. Inform LLM about prior context
# """

# import sys
# import logging
# from pathlib import Path
# from pydantic import BaseModel
# from typing import Literal

# # Try shared logger
# try:
#     shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
#     if str(shared_path) not in sys.path:
#         sys.path.insert(0, str(shared_path))
#     from utils import get_logger
# except ImportError:
#     logging.basicConfig(level=logging.INFO)
#     def get_logger(name):
#         return logging.getLogger(name)

# # Add RAG path
# rag_path = Path(__file__).parent.parent.parent / "rag"
# if str(rag_path) not in sys.path:
#     sys.path.insert(0, str(rag_path))

# from src.rag.scenario_loader import get_scenario_loader
# from src.rag.retriever import get_retriever

# from src.services.llm import llm_json_completion
# from src.services.config_loader import load_config
# from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

# logger = get_logger(__name__)


# # =============================================================================
# # HELP REQUEST DETECTION
# # =============================================================================

# def detect_help_request(user_message: str) -> bool:
#     """
#     Detect if user is asking for help with current instruction.
    
#     Args:
#         user_message: User's message
        
#     Returns:
#         True if user needs help/explanation
#     """
#     help_phrases = [
#         # Lithuanian
#         "kaip tai padaryti",
#         "kaip tai",
#         "kaip?",
#         "nežinau kaip",
#         "nezinau kaip",
#         "padėk",
#         "padek",
#         "paaiškink",
#         "paaiskink",
#         "nemoku",
#         "nesuprantu",
#         "kur rasti",
#         "kur yra",
#         "kas tai",
#         "ką reiškia",
#         "ka reiskia",
#         "kur tai",
#         "kaip surasti",
#         "kaip rasti",
#         "kaip patikrinti",
#         "neįmanoma",
#         "neimanoma",
#         "per sunku",
#         "nesigauna",
#         # English fallback
#         "how to",
#         "how do i",
#         "what is",
#         "where is",
#         "help me",
#     ]
    
#     msg_lower = user_message.lower().strip()
    
#     # Direct match
#     if any(phrase in msg_lower for phrase in help_phrases):
#         return True
    
#     # Short confused responses
#     if msg_lower in ["?", "??", "kas", "kur", "kaip", "ką", "ka"]:
#         return True
    
#     return False


# def generate_help_response(current_step: dict, help_topic: str = None) -> str:
#     """
#     Generate detailed help instructions for current troubleshooting step.
    
#     Args:
#         current_step: Current step dict with title and instruction
#         help_topic: Specific topic user asked about (optional)
        
#     Returns:
#         Detailed help message in Lithuanian
#     """
#     step_title = current_step.get("title", "").lower()
#     step_instruction = current_step.get("instruction", "")
    
#     # WiFi check help
#     if "wifi" in step_title or "wifi" in step_instruction.lower():
#         return """Suprantu, padėsiu! Štai kaip patikrinti WiFi telefone:

# **Android telefone:**
# 1. Atidarykite "Nustatymai" (Settings) - dažniausiai krumpliaračio ikona
# 2. Paspauskite "WiFi" arba "Tinklas ir internetas"
# 3. Patikrinkite ar WiFi jungiklis ĮJUNGTAS (turi būti žalias/mėlynas)
# 4. Jei įjungtas - ar matote savo namų tinklo pavadinimą?

# **iPhone telefone:**
# 1. Atidarykite "Settings" (Nustatymai)
# 2. Paspauskite "Wi-Fi"
# 3. Patikrinkite ar jungiklis žalias (įjungtas)
# 4. Ar matote savo tinklo pavadinimą su varnele?

# Pasakykite man, ar WiFi įjungtas ir ar matote savo tinklą sąraše?"""

#     # Router lights help
#     if "lemput" in step_title or "lemput" in step_instruction.lower() or "šviesos" in step_instruction.lower():
#         return """Suprantu, padėsiu! Routerio lempučių tikrinimas:

# **Kur rasti routerį:**
# - Paprastai stovi prie kompiuterio arba prie telefono lizdo
# - Tai dėžutė su keliomis šviečiančiomis lempučių

# **Ką tikrinti:**
# 1. **POWER** lempute - ar dega? (rodo kad routeris įjungtas)
# 2. **INTERNET** arba **WAN** lempute - ar dega? (rodo interneto ryšį)
# 3. **WiFi** lempute - ar dega? (rodo belaidį tinklą)

# Jei visos lemputes dega žaliai - routeris veikia gerai.
# Jei kuri nors nedega arba mirksi raudonai - gali būti problema.

# Pasakykite, kokios spalvos dega lemputes?"""

#     # Router restart help
#     if "perkrau" in step_title or "perkrau" in step_instruction.lower() or "restart" in step_instruction.lower():
#         return """Suprantu, padėsiu perkrauti routerį:

# **Kaip perkrauti:**
# 1. Raskite routerio maitinimo laidą (juodas laidas einantis į rozetę)
# 2. Ištraukite laidą iš rozetės
# 3. Palaukite 30 sekundžių
# 4. Įjunkite laidą atgal į rozetę
# 5. Palaukite 2-3 minutes kol routeris pilnai įsijungs

# **Kaip žinoti kad įsijungė:**
# - Lemputes nustos mirksėti ir degs stabiliai
# - Tai užtrunka apie 2-3 minutes

# Ar pavyko perkrauti? Pasakykite kai lemputes nustos mirksėti."""

#     # Cable check help
#     if "kabel" in step_title or "kabel" in step_instruction.lower() or "laid" in step_instruction.lower():
#         return """Suprantu, padėsiu patikrinti kabelius:

# **Kokie kabeliai:**
# 1. **Maitinimo laidas** - juodas, eina į rozetę
# 2. **Interneto laidas** - dažniausiai geltonas arba pilkas, eina į sieną arba modemą
# 3. **LAN kabelis** - jei kompiuteris prijungtas laidu

# **Ką tikrinti:**
# - Ar visi kabeliai tvirtai įkišti?
# - Ar nėra pažeistų/perlenktų vietų?
# - Pabandykite ištraukti ir vėl įkišti kiekvieną kabelį

# Ar visi kabeliai tvirtai prijungti?"""

#     # Generic help
#     return f"""Suprantu, kad reikia daugiau paaiškinimo.

# Dabartinis žingsnis: {current_step.get('title', 'Troubleshooting')}

# {step_instruction}

# Jei kažkas neaišku - pasakykite konkrečiai kas, ir pabandysiu paaiškinti paprasčiau."""


# # =============================================================================
# # FRUSTRATION DETECTION
# # =============================================================================

# def detect_frustration(user_message: str) -> dict:
#     """
#     Detect if user is frustrated, annoyed, or pointing out bot mistakes.
    
#     Args:
#         user_message: User's message
        
#     Returns:
#         Dict with frustration analysis
#     """
#     msg_lower = user_message.lower().strip()
    
#     # Frustration phrases - user is annoyed
#     frustration_phrases = [
#         "negali padėti", "negali padeti",
#         "nepadedi", "nepadeda",
#         "nenaudingas", "nenaudinga",
#         "blogas", "bloga",
#         "neveikia", "neveikia šitas",
#         "kvailas", "kvaila",
#         "beprasmis", "beprasme",
#         "gaila laiko",
#         "nesąmonė", "nesamone",
#         "atsibodo",
#         "pakaks", "gana",
#         "užtenka", "uztenka",
#     ]
    
#     # Repetition complaints - user says we're repeating
#     repetition_phrases = [
#         "jau sakiau",
#         "jau minėjau", "jau minejau",
#         "jau atsakiau",
#         "kartoji", "kartojat",
#         "vėl tas pats", "vel tas pats",
#         "tą patį", "ta pati",
#         "neatsimeni",
#         "pamiršai", "pamirso",
#         "kiek kartų", "kiek kartu",
#         "trečią kartą", "trecia karta",
#         "antrą kartą", "antra karta",
#     ]
    
#     # Escalation requests - user wants human
#     escalation_phrases = [
#         "noriu žmogaus", "noriu zmogaus",
#         "noriu operatorius",
#         "noriu kalbėti su",
#         "sujunkite su",
#         "perduokite",
#         "tikrą žmogų", "tikra zmogu",
#         "gyvą žmogų", "gyva zmogu",
#         "vadovą", "vadova",
#         "techniką", "technika",
#     ]
    
#     is_frustrated = any(phrase in msg_lower for phrase in frustration_phrases)
#     is_repetition_complaint = any(phrase in msg_lower for phrase in repetition_phrases)
#     wants_escalation = any(phrase in msg_lower for phrase in escalation_phrases)
    
#     # Determine severity
#     severity = 0
#     if is_repetition_complaint:
#         severity += 1
#     if is_frustrated:
#         severity += 2
#     if wants_escalation:
#         severity += 3
    
#     return {
#         "is_frustrated": is_frustrated,
#         "is_repetition_complaint": is_repetition_complaint,
#         "wants_escalation": wants_escalation,
#         "severity": severity,  # 0=none, 1=mild, 2=moderate, 3+=severe
#         "should_apologize": is_frustrated or is_repetition_complaint,
#         "should_summarize": is_repetition_complaint,
#         "should_escalate": wants_escalation or severity >= 4,
#     }


# def generate_apology_response(frustration: dict, checked_items: dict, problem_description: str) -> str:
#     """
#     Generate appropriate apology response based on frustration type.
    
#     Args:
#         frustration: Frustration analysis dict
#         checked_items: What we've already checked
#         problem_description: Original problem
        
#     Returns:
#         Apology message
#     """
#     # Build summary of what we know
#     summary_parts = []
#     if checked_items:
#         if "router_lights" in checked_items:
#             summary_parts.append(f"routerio lemputes: {checked_items['router_lights']}")
#         if checked_items.get("router_restarted"):
#             summary_parts.append("routeris perkrautas")
#         if "wifi_status" in checked_items:
#             summary_parts.append(f"WiFi: {checked_items['wifi_status']}")
#         if "device_wifi" in checked_items:
#             summary_parts.append(f"įrenginio WiFi: {checked_items['device_wifi']}")
    
#     summary = ", ".join(summary_parts) if summary_parts else "turite interneto problemą"
    
#     # Repetition complaint response
#     if frustration.get("is_repetition_complaint"):
#         return f"""Labai atsiprašau, kad kartoju klausimus! Turite visišką teisę pykti.

# Apibendrinu ką jau žinome:
# • Problema: {problem_description}
# • Jau patikrinta: {summary}

# Pabandykime kitaip - ar galite pasakyti, ar dabar telefone matote WiFi tinklo pavadinimą ir ar prie jo prisijungęs?"""

#     # General frustration response
#     if frustration.get("is_frustrated"):
#         return f"""Atsiprašau, kad nepavyksta greitai išspręsti problemos. Suprantu jūsų nusivylimą.

# Ką žinome: {summary}

# Ar norėtumėte, kad sukurčiau užklausą technikui? Jis galėtų paskambinti ir padėti išsamiau."""

#     # Escalation request response
#     if frustration.get("wants_escalation"):
#         return """Suprantu, sukursiu užklausą ir mūsų specialistas su jumis susisieks artimiausiu metu.

# Ar yra konkretus laikas, kada būtų patogiau sulaukti skambučio?"""

#     # Default
#     return "Atsiprašau už nepatogumus. Pabandykime dar kartą."


# # === LLM Response Schemas ===

# class ScenarioSelection(BaseModel):
#     """LLM response for selecting scenario."""
#     scenario_id: str
#     confidence: float  # 0-1
#     reasoning: str


# class StepResponse(BaseModel):
#     """LLM response for analyzing user answer to troubleshooting step."""
#     understood: bool
#     user_answer_summary: str
#     selected_branch: str | None = None
#     needs_clarification: bool = False
#     clarification_question: str | None = None
#     needs_next_substep: bool = False
#     next_substep_instruction: str | None = None
#     # NEW: Track what was checked in this response
#     extracted_checks: dict = {}  # {"router_lights": "žalios", "router_restarted": true}


# # =============================================================================
# # CONTEXT INTEGRATION FUNCTIONS
# # =============================================================================

# def get_troubleshooting_mappings() -> dict:
#     """Load troubleshooting mappings config."""
#     try:
#         return load_config("troubleshooting_mappings")
#     except FileNotFoundError:
#         logger.warning("troubleshooting_mappings.yaml not found, using defaults")
#         return {}


# def build_context_summary(problem_context: dict, problem_type: str) -> str:
#     """
#     Build human-readable summary of what we know from problem_context.
    
#     Args:
#         problem_context: Dict with extracted facts from problem capture
#         problem_type: internet/tv/phone
        
#     Returns:
#         Summary string for LLM context
#     """
#     if not problem_context:
#         return ""
    
#     summary_parts = []
    
#     # Duration
#     duration = problem_context.get("duration")
#     if duration:
#         summary_parts.append(f"Problema prasidėjo: {duration}")
    
#     # Scope
#     scope = problem_context.get("scope")
#     if scope:
#         if scope in ["visi", "visur", "visuose", "all_devices"]:
#             summary_parts.append("Problema visuose įrenginiuose")
#         else:
#             summary_parts.append(f"Paveikti įrenginiai: {scope}")
    
#     # Restart attempt
#     tried_restart = problem_context.get("tried_restart")
#     if tried_restart is True:
#         summary_parts.append("Klientas JAU BANDĖ perkrauti routerį - NEKLAUSK dar kartą!")
#     elif tried_restart is False:
#         summary_parts.append("Klientas DAR NEBANDĖ perkrauti routerio")
    
#     # Router lights
#     router_lights = problem_context.get("router_lights")
#     if router_lights:
#         if router_lights in ["nedega", "off", "nėra"]:
#             summary_parts.append("Routerio lemputos NEDEGA - tikėtina maitinimo problema")
#         elif router_lights in ["dega", "on", "žalia", "green"]:
#             summary_parts.append("Routerio lemputos dega")
#         else:
#             summary_parts.append(f"Routerio lemputos: {router_lights}")
    
#     # WiFi visibility
#     wifi_visible = problem_context.get("wifi_visible")
#     if wifi_visible is True:
#         summary_parts.append("Klientas mato WiFi tinklą")
#     elif wifi_visible is False:
#         summary_parts.append("Klientas NEMATO WiFi tinklo")
    
#     # TV specific
#     decoder_status = problem_context.get("decoder_status")
#     if decoder_status:
#         summary_parts.append(f"Dekoderio būklė: {decoder_status}")
    
#     has_image = problem_context.get("has_image")
#     if has_image is False:
#         summary_parts.append("Nėra vaizdo ekrane")
    
#     has_sound = problem_context.get("has_sound")
#     if has_sound is False:
#         summary_parts.append("Nėra garso")
    
#     if not summary_parts:
#         return ""
    
#     return "ŽINOMA INFORMACIJA IŠ ANKSTESNIO POKALBIO:\n- " + "\n- ".join(summary_parts)


# def build_checked_items_summary(checked_items: dict) -> str:
#     """
#     Build summary of items already checked during troubleshooting.
#     This is CRITICAL to prevent repeating questions.
    
#     Args:
#         checked_items: Dict of items already checked
        
#     Returns:
#         Summary string for LLM - emphatic about not repeating
#     """
#     if not checked_items:
#         return ""
    
#     summary_parts = []
    
#     # Router lights
#     if "router_lights" in checked_items:
#         value = checked_items["router_lights"]
#         summary_parts.append(f"🔴 LEMPUTES JAU PATIKRINTOS: {value}")
    
#     # Router restart
#     if checked_items.get("router_restarted"):
#         summary_parts.append("🔴 ROUTERIS JAU PERKRAUTAS")
    
#     # WiFi check
#     if "wifi_status" in checked_items:
#         value = checked_items["wifi_status"]
#         summary_parts.append(f"🔴 WIFI JAU PATIKRINTAS: {value}")
    
#     # Device WiFi
#     if "device_wifi" in checked_items:
#         value = checked_items["device_wifi"]
#         summary_parts.append(f"🔴 ĮRENGINIO WIFI: {value}")
    
#     # Power check
#     if "power_checked" in checked_items:
#         summary_parts.append("🔴 MAITINIMAS JAU PATIKRINTAS")
    
#     # Cable check
#     if "cables_checked" in checked_items:
#         summary_parts.append("🔴 KABELIAI JAU PATIKRINTI")
    
#     # Any other items
#     standard_keys = {"router_lights", "router_restarted", "wifi_status", "device_wifi", "power_checked", "cables_checked"}
#     for key, value in checked_items.items():
#         if key not in standard_keys:
#             summary_parts.append(f"🔴 {key.upper()}: {value}")
    
#     if not summary_parts:
#         return ""
    
#     return """
# ⚠️⚠️⚠️ KRITIŠKAI SVARBU - JAU PATIKRINTA (NIEKADA NEKARTOTI!): ⚠️⚠️⚠️
# """ + "\n".join(summary_parts) + """

# JEIGU KLAUSI APIE KAŽKĄ KAS JAU PATIKRINTA - TAI KLAIDA!
# """


# def determine_starting_step(scenario, problem_context: dict, problem_type: str, diagnostic_results: dict = None) -> dict:
#     """
#     Determine which step to start from based on problem_context AND diagnostic_results.
    
#     Args:
#         scenario: Loaded scenario object
#         problem_context: Dict with extracted facts from problem capture
#         problem_type: internet/tv/phone
#         diagnostic_results: Results from diagnostics node (port status, IP assignment, etc.)
        
#     Returns:
#         Step dict to start from (may skip initial steps)
#     """
    
#     # ===========================================
#     # PRIORITY 1: Check diagnostic_results first
#     # ===========================================
#     if diagnostic_results:
#         ip_check = diagnostic_results.get("ip_assignment_check", {})
#         port_check = diagnostic_results.get("port_status_check", {})
        
#         # Router confirmed working if:
#         # - IP is assigned and active
#         # - Port is up
#         ip_active = ip_check.get("success") and ip_check.get("active_count", 0) > 0
#         port_healthy = port_check.get("diagnostics", {}).get("all_ports_healthy", False)
        
#         router_confirmed_working = ip_active and port_healthy
        
#         if router_confirmed_working:
#             logger.info("✅ Diagnostics confirm router is working - skipping router checks")
#             logger.info(f"   IP active: {ip_active}, Port healthy: {port_healthy}")
            
#             # Try to find device check step
#             device_step = scenario.get_step("step_4") or scenario.get_step("device_check")
#             if device_step:
#                 logger.info(f"   → Starting from step: {device_step.get('step_id', 'device_check')}")
#                 return device_step
    
#     # ===========================================
#     # PRIORITY 2: Check scope (single device)
#     # ===========================================
#     if problem_context:
#         scope = str(problem_context.get("scope", "")).lower()
#         single_device_keywords = ["telefonas", "phone", "kompiuteris", "laptop", "vienas", "tik vienas"]
        
#         is_single_device = any(kw in scope for kw in single_device_keywords)
        
#         if is_single_device:
#             logger.info(f"✅ Single device affected: '{scope}' - skipping router checks")
#             device_step = scenario.get_step("step_4") or scenario.get_step("device_check")
#             if device_step:
#                 return device_step
    
#     # ===========================================
#     # PRIORITY 3: Check problem_context facts
#     # ===========================================
#     if not problem_context:
#         return scenario.get_first_step()
    
#     mappings = get_troubleshooting_mappings()
#     rules = mappings.get("context_to_skip_rules", {}).get(problem_type, [])
#     step_aliases = mappings.get("step_aliases", {})
    
#     # Find matching rule
#     best_match = None
#     best_match_score = 0
    
#     for rule in rules:
#         condition = rule.get("condition", {})
#         match_score = 0
#         all_conditions_met = True
        
#         for field, expected_value in condition.items():
#             actual_value = problem_context.get(field)
            
#             if actual_value is None:
#                 all_conditions_met = False
#                 break
            
#             if isinstance(expected_value, bool):
#                 if actual_value == expected_value:
#                     match_score += 1
#                 else:
#                     all_conditions_met = False
#                     break
#             elif isinstance(expected_value, str):
#                 actual_str = str(actual_value).lower()
#                 expected_str = expected_value.lower()
#                 if expected_str in actual_str or actual_str in expected_str:
#                     match_score += 1
#                 elif expected_str == "dega" and any(x in actual_str for x in ["dega", "žalia", "green", "on", "šviečia"]):
#                     match_score += 1
#                 elif expected_str == "nedega" and any(x in actual_str for x in ["nedega", "off", "nėra", "tamsu"]):
#                     match_score += 1
#                 else:
#                     all_conditions_met = False
#                     break
        
#         if all_conditions_met and match_score > best_match_score:
#             best_match = rule
#             best_match_score = match_score
    
#     if best_match:
#         start_from = best_match.get("start_from")
#         reason = best_match.get("reason", "")
#         skip_steps = best_match.get("skip_steps", [])
        
#         logger.info(f"Context match: {reason}")
#         logger.info(f"Skipping steps: {skip_steps}, starting from: {start_from}")
        
#         if start_from:
#             scenario_id = scenario.scenario_id if hasattr(scenario, 'scenario_id') else ""
#             aliases = step_aliases.get(scenario_id, {})
#             actual_step_id = aliases.get(start_from, start_from)
            
#             step = scenario.get_step(actual_step_id)
#             if step:
#                 return step
            
#             try:
#                 step_num = int(start_from.replace("step_", ""))
#                 step = scenario.get_step(f"step_{step_num}")
#                 if step:
#                     return step
#             except (ValueError, AttributeError):
#                 pass
    
#     # Default: start from first step
#     return scenario.get_first_step()


# def get_skipped_steps_message(problem_context: dict, problem_type: str) -> str:
#     """
#     Generate message explaining why we're skipping steps.
    
#     Args:
#         problem_context: Dict with extracted facts
#         problem_type: internet/tv/phone
        
#     Returns:
#         Message string or empty
#     """
#     parts = []
    
#     tried_restart = problem_context.get("tried_restart")
#     router_lights = problem_context.get("router_lights")
    
#     if tried_restart is True:
#         parts.append("jau bandėte perkrauti routerį")
    
#     if router_lights:
#         lights_str = str(router_lights).lower()
#         if any(x in lights_str for x in ["nedega", "off", "nėra"]):
#             parts.append("lemputes nedega")
#         elif any(x in lights_str for x in ["dega", "on", "žalia"]):
#             parts.append("lemputes dega")
    
#     if parts:
#         return f"Kadangi {', '.join(parts)}, praleisime kai kuriuos žingsnius."
    
#     return ""


# # =============================================================================
# # HELPER FUNCTIONS (existing)
# # =============================================================================

# def _get_troubleshooting_state(state) -> dict:
#     """Get troubleshooting state from conversation state."""
#     scenario_id = _get_attr(state, "troubleshooting_scenario_id")
#     current_step = _get_attr(state, "troubleshooting_current_step")
#     completed_steps = _get_attr(state, "troubleshooting_completed_steps")
#     skipped_steps = _get_attr(state, "troubleshooting_skipped_steps")
#     checked_items = _get_attr(state, "troubleshooting_checked_items")
    
#     return {
#         "scenario_id": scenario_id,
#         "current_step": current_step if current_step else 1,
#         "completed_steps": completed_steps if completed_steps else [],
#         "skipped_steps": skipped_steps if skipped_steps else [],
#         "checked_items": checked_items if checked_items else {},
#     }


# def select_scenario(problem_description: str, problem_type: str) -> str:
#     """
#     Select appropriate troubleshooting scenario using RAG.
#     Includes smart fallback if problem_type is 'other'.
#     """
#     logger.info(f"Selecting scenario for: {problem_description} (type: {problem_type})")
    
#     # Smart fallback: if "other" but description suggests specific type
#     actual_type = problem_type
#     if problem_type == "other" and problem_description:
#         desc_lower = problem_description.lower()
        
#         # Check for internet-related keywords
#         internet_keywords = ["internet", "internetas", "naršyklė", "narsykle", "wifi", 
#                            "prisijung", "ryšys", "rysys", "tinklas", "router", "maršrutizator"]
#         if any(kw in desc_lower for kw in internet_keywords):
#             actual_type = "internet"
#             logger.info(f"Smart fallback: 'other' → 'internet' (detected from description)")
        
#         # Check for TV-related keywords
#         tv_keywords = ["televizor", "tv", "kanal", "dekoder", "vaizdas", "ekran"]
#         if any(kw in desc_lower for kw in tv_keywords):
#             actual_type = "tv"
#             logger.info(f"Smart fallback: 'other' → 'tv' (detected from description)")
        
#         # Check for phone-related keywords
#         phone_keywords = ["telefon", "skamb", "linija", "ragelis"]
#         if any(kw in desc_lower for kw in phone_keywords):
#             actual_type = "phone"
#             logger.info(f"Smart fallback: 'other' → 'phone' (detected from description)")
    
#     retriever = get_retriever()
    
#     try:
#         success = retriever.load("production")
#         if success:
#             logger.info("Loaded production knowledge base")
#     except Exception as e:
#         logger.error(f"Error loading production KB: {e}")
    
#     query = f"{actual_type} {problem_description}"
#     results = retriever.retrieve(
#         query=query,
#         top_k=3,
#         threshold=0.5,
#         filter_metadata={"type": "scenario", "problem_type": actual_type}
#     )
    
#     if results:
#         best_match = results[0]
#         scenario_id = best_match["metadata"]["scenario_id"]
#         logger.info(f"Selected scenario: {scenario_id} (score: {best_match['score']:.3f})")
#         return scenario_id
    
#     # Fallback to default based on actual_type (not original problem_type)
#     logger.warning(f"No scenario found for {actual_type}, using default")
    
#     # Map to existing scenarios
#     default_scenarios = {
#         "internet": "internet_no_connection",
#         "tv": "tv_no_signal",
#         "phone": "internet_no_connection",  # Fallback if no phone scenario
#         "billing": "internet_no_connection",  # Fallback
#         "other": "internet_no_connection",  # Ultimate fallback
#     }
    
#     return default_scenarios.get(actual_type, "internet_no_connection")


# def format_step_instruction(step: dict, customer_name: str = "", is_first_time: bool = True) -> str:
#     """
#     Format step instruction for customer - ONE SUB-TASK AT A TIME.
#     """
#     title = step.get("title", "")
#     instruction = step.get("instruction", "")
    
#     if customer_name:
#         first_name = customer_name.split()[0]
#         greeting = f"{first_name}, "
#     else:
#         greeting = ""
    
#     if not is_first_time:
#         return instruction
    
#     system_prompt = """Tu esi ISP klientų aptarnavimo asistentas telefono pokalbyje.

# LABAI SVARBU:
# - Tai telefoninis pokalbis - klientas negali matyti teksto
# - Duok tik VIENĄ veiksmą per kartą
# - Paprašyk padaryti vieną dalyką ir pasakyti rezultatą

# Iš šios instrukcijos ištrauk tik PIRMĄ veiksmą kurį klientas turi padaryti:

# {instruction}

# Atsakyk trumpai ir aiškiai - tik pirmas veiksmas, vienas sakinys."""

#     try:
#         from src.services.llm import llm_completion
        
#         messages = [
#             {"role": "system", "content": system_prompt.format(instruction=instruction)},
#             {"role": "user", "content": "Koks pirmas veiksmas?"}
#         ]
        
#         first_action = llm_completion(messages, temperature=0.2, max_tokens=150)
#         return f"{greeting}{first_action}"
        
#     except Exception as e:
#         logger.warning(f"Could not simplify instruction: {e}")
#         sentences = instruction.split('. ')
#         first_part = '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else instruction
#         return f"{greeting}{first_part}"


# def analyze_user_response(step: dict, user_response: str, recent_messages: list = None, context_summary: str = "", checked_items: dict = None) -> StepResponse:
#     """
#     Use LLM to analyze user's response and guide step-by-step.
#     Now includes context_summary from problem_context AND checked_items tracking.
#     """
#     branches = step.get("branches", {})
#     instruction = step.get("instruction", "")
#     title = step.get("title", "")
    
#     conversation_context = ""
#     if recent_messages:
#         conversation_context = "ANKSTESNĖ POKALBIO DALIS (šiame žingsnyje):\n"
#         for msg in recent_messages[-10:]:
#             role = "Agentas" if msg.get("role") == "assistant" else "Klientas"
#             conversation_context += f"{role}: {msg.get('content', '')}\n"
#         conversation_context += "\n---\n"
    
#     # Add problem_context info
#     prior_knowledge = ""
#     if context_summary:
#         prior_knowledge = f"""
# {context_summary}

# SVARBU: Naudok šią informaciją! Jei klientas JAU kažką bandė - neklausinėk to paties!
# ---
# """
    
#     # Add checked items - CRITICAL for not repeating
#     checked_items_section = ""
#     if checked_items:
#         checked_items_section = build_checked_items_summary(checked_items)
    
#     system_prompt = f"""Tu esi ISP klientų aptarnavimo asistentas TELEFONO pokalbyje.

# {prior_knowledge}
# {checked_items_section}

# KONTEKSTAS:
# - Tai telefoninis pokalbis - klientas NEGALI matyti ankstesnių žinučių
# - Vesk klientą PO VIENĄ veiksmą - vienas veiksmas, vienas atsakymas
# - Būk kantrus, aiškus, draugiškas
# - ⚠️ KRITIŠKAI SVARBU: Atsimink ką klientas JAU patikrino ir NIEKADA NEKARTOK tų pačių klausimų!
# - Jei "JAU PATIKRINTA" sekcijoje yra "LEMPUTES" - NEKLAUSTI apie lemputes!
# - Jei "JAU PATIKRINTA" sekcijoje yra "PERKRAUTAS" - NEPRAŠYTI perkrauti!

# {conversation_context}

# DABARTINIS ŽINGSNIS: {title}

# PILNA INSTRUKCIJA (ką reikia patikrinti šiame žingsnyje):
# {instruction}

# GALIMI REZULTATAI kai žingsnis BAIGTAS:
# {chr(10).join([f"- {branch_id}: {branch_data.get('condition')}" for branch_id, branch_data in branches.items()])}

# DABAR KLIENTAS ATSAKĖ: "{user_response}"

# TAVO UŽDUOTIS:
# 1. Peržiūrėk "JAU PATIKRINTA" sekciją - ŠIŲ DALYKŲ NEKARTOTI!
# 2. Peržiūrėk pokalbio istoriją - kas dar patikrinta?
# 3. Ištrauk naują informaciją iš kliento atsakymo į "extracted_checks"
# 4. Jei reikia daugiau info - klausk TIK to, kas DAR NEPATIKRINTA
# 5. Jei viskas patikrinta - pasirink tinkamą branch

# Atsakyk JSON formatu:
# {{
#     "understood": true,
#     "user_answer_summary": "trumpai ką klientas pasakė/padarė",
#     "selected_branch": "branch_id JEI žingsnis baigtas, ARBA null",
#     "needs_clarification": false,
#     "clarification_question": null,
#     "needs_next_substep": true/false,
#     "next_substep_instruction": "JEI reikia dar vieno veiksmo - trumpa instrukcija, ARBA null",
#     "extracted_checks": {{
#         "router_lights": "žalios/raudonos/nedega JEI klientas pasakė",
#         "router_restarted": true JEI klientas perkrovė,
#         "wifi_status": "įjungtas/išjungtas JEI klientas pasakė",
#         "device_wifi": "prisijungęs/neprisijungęs JEI klientas pasakė"
#     }}
# }}

# PAVYZDYS - jei klientas sako "lemputes dega žaliai":
# {{
#     "understood": true,
#     "user_answer_summary": "Visos lemputes dega žaliai",
#     "extracted_checks": {{"router_lights": "visos žalios"}},
#     ...
# }}"""

#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user", "content": user_response}
#     ]
    
#     try:
#         response = llm_json_completion(messages, temperature=0.3, max_tokens=500)
#         return StepResponse(**response)
#     except Exception as e:
#         logger.error(f"Error analyzing response: {e}")
#         return StepResponse(
#             understood=False,
#             user_answer_summary=user_response,
#             needs_clarification=True,
#             clarification_question="Atsiprašau, ar galėtumėte pakartoti ką matote?"
#         )


# # =============================================================================
# # MAIN NODE FUNCTION
# # =============================================================================

# def troubleshooting_node(state) -> dict:
#     """
#     Troubleshooting node v2 - guides customer through troubleshooting steps.
    
#     Now integrates problem_context to:
#     - Skip steps customer already tried
#     - Start from appropriate step
#     - Inform LLM about prior context
#     """
#     logger.info("=== Troubleshooting Node v2 ===")
    
#     # Check if problem already resolved - skip processing
#     if _get_attr(state, "problem_resolved", False):
#         logger.info("Problem already resolved - passing through to router")
#         return {"current_node": "troubleshooting"}
    
#     # Check if already needs escalation - skip processing
#     if _get_attr(state, "troubleshooting_needs_escalation", False):
#         logger.info("Already needs escalation - passing through to router")
#         return {"current_node": "troubleshooting"}
    
#     ts_state = _get_troubleshooting_state(state)
#     problem_description = _get_attr(state, "problem_description", "")
#     problem_type = _get_attr(state, "problem_type", "internet")
#     problem_context = _get_attr(state, "problem_context", {})
#     diagnostic_results = _get_attr(state, "diagnostic_results", {})  # ← NEW
#     customer_name = _get_attr(state, "customer_name", "")
    
#     # Build context summary for LLM
#     context_summary = build_context_summary(problem_context, problem_type)
#     if context_summary:
#         logger.info(f"Context summary:\n{context_summary}")
    
#     # Check if first time in troubleshooting
#     if not ts_state["scenario_id"]:
#         logger.info("First time in troubleshooting - selecting scenario")
        
#         # Select scenario
#         scenario_id = select_scenario(problem_description, problem_type)
        
#         # Load scenario
#         scenario_loader = get_scenario_loader()
#         scenario = scenario_loader.get_scenario(scenario_id)
        
#         if not scenario:
#             logger.error(f"Scenario not found: {scenario_id}")
#             error_msg = add_message(
#                 role="assistant",
#                 content="Atsiprašau, nepavyko rasti tinkamo sprendimo scenarijaus. Sukursiu techninės pagalbos užklausą.",
#                 node="troubleshooting"
#             )
#             return {
#                 "messages": [error_msg],
#                 "current_node": "troubleshooting",
#                 "troubleshooting_needs_escalation": True,
#                 "troubleshooting_escalation_reason": "scenario_not_found",
#             }
        
#         # ========================================
#         # NEW: Determine starting step based on context AND diagnostics
#         # ========================================
#         starting_step = determine_starting_step(scenario, problem_context, problem_type, diagnostic_results)
#         first_step = scenario.get_first_step()
        
#         skipped_steps = []
#         skip_message = ""
        
#         # Check if we're skipping steps
#         if starting_step.get("step_id") != first_step.get("step_id"):
#             logger.info(f"Skipping to step: {starting_step.get('step_id')} (was: {first_step.get('step_id')})")
            
#             # Collect skipped step IDs
#             # (simplified - in real impl would walk through scenario)
#             skip_message = get_skipped_steps_message(problem_context, problem_type)
            
#             # Mark steps as skipped
#             try:
#                 first_step_num = int(first_step.get("step_id", "step_1").replace("step_", ""))
#                 start_step_num = int(starting_step.get("step_id", "step_1").replace("step_", ""))
#                 skipped_steps = [f"step_{i}" for i in range(first_step_num, start_step_num)]
#             except ValueError:
#                 pass
        
#         # Format instruction
#         instruction_text = format_step_instruction(starting_step, customer_name)
        
#         # Build message
#         intro = "Gerai, pabandykime išspręsti problemą kartu."
#         if skip_message:
#             intro = f"Gerai, pabandykime išspręsti problemą. {skip_message}"
        
#         message = add_message(
#             role="assistant",
#             content=f"{intro}\n\n**{starting_step.get('title')}**\n\n{instruction_text}",
#             node="troubleshooting"
#         )
        
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_scenario_id": scenario_id,
#             "troubleshooting_current_step": starting_step.get("step_id"),
#             "troubleshooting_completed_steps": [],
#             "troubleshooting_skipped_steps": skipped_steps,
#         }
    
#     # Get user response
#     user_response = get_last_user_message(state)
#     logger.info(f"Analyzing user response: {user_response}")
    
#     # ===========================================
#     # CHECK FOR HELP REQUEST FIRST
#     # ===========================================
#     if detect_help_request(user_response):
#         logger.info("🆘 Help request detected - generating help response")
        
#         # Load current step for context
#         scenario_loader = get_scenario_loader()
#         scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
#         current_step = scenario.get_step(ts_state["current_step"]) if scenario else {}
        
#         help_response = generate_help_response(current_step, user_response)
        
#         message = add_message(
#             role="assistant",
#             content=help_response,
#             node="troubleshooting"
#         )
        
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_checked_items": ts_state.get("checked_items", {}),
#         }
    
#     # ===========================================
#     # CHECK FOR FRUSTRATION
#     # ===========================================
#     frustration = detect_frustration(user_response)
    
#     if frustration.get("should_escalate"):
#         logger.info("😤 User wants escalation - creating ticket")
        
#         message = add_message(
#             role="assistant",
#             content="Suprantu, sukursiu užklausą ir mūsų specialistas su jumis susisieks artimiausiu metu. Atsiprašau už nepatogumus.",
#             node="troubleshooting"
#         )
        
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_needs_escalation": True,
#             "troubleshooting_escalation_reason": "customer_requested",
#             "troubleshooting_checked_items": ts_state.get("checked_items", {}),
#         }
    
#     if frustration.get("should_apologize"):
#         logger.info(f"😤 Frustration detected: {frustration}")
        
#         problem_description = _get_attr(state, "problem_description", "interneto problema")
#         checked_items = ts_state.get("checked_items", {})
        
#         apology_response = generate_apology_response(frustration, checked_items, problem_description)
        
#         message = add_message(
#             role="assistant",
#             content=apology_response,
#             node="troubleshooting"
#         )
        
#         # If severity is high, consider escalation
#         if frustration.get("severity", 0) >= 3:
#             return {
#                 "messages": [message],
#                 "current_node": "troubleshooting",
#                 "troubleshooting_needs_escalation": True,
#                 "troubleshooting_escalation_reason": "customer_frustrated",
#                 "troubleshooting_checked_items": checked_items,
#             }
        
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_checked_items": checked_items,
#         }

#     # Check for goodbye/confirmation phrases BEFORE LLM analysis
#     goodbye_phrases = [
#         "ačiū", "aciu", "viso gero", "iki", "sudie",
#         "viskas gerai", "nieko daugiau", "nereikia",
#         "ne ačiū", "ne aciu", "ne, ačiū", "ne, aciu",
#         "viskas", "pakanka", "užtenka"
#     ]
    
#     user_lower = user_response.lower()
#     is_goodbye = any(phrase in user_lower for phrase in goodbye_phrases)
    
#     # Check if problem was just resolved in previous turn
#     messages = _get_messages(state)
#     recent_assistant_msgs = [m for m in messages if m.get("role") == "assistant"][-3:]
#     problem_just_resolved = any(
#         "išspręsta" in m.get("content", "").lower() or
#         "pavyko" in m.get("content", "").lower() or
#         "veikia" in m.get("content", "").lower()
#         for m in recent_assistant_msgs
#     )
    
#     if is_goodbye and problem_just_resolved:
#         logger.info("User confirming goodbye after resolution → create_ticket (silent)")
#         completed = ts_state.get("completed_steps", [])
#         return {
#             "current_node": "troubleshooting",
#             "problem_resolved": True,
#             "troubleshooting_completed_steps": completed,
#         }
    
#     # Load current scenario and step
#     scenario_loader = get_scenario_loader()
#     scenario = scenario_loader.get_scenario(ts_state["scenario_id"])
#     current_step = scenario.get_step(ts_state["current_step"])
    
#     if not current_step:
#         logger.error(f"Current step not found: {ts_state['current_step']}")
#         return {
#             "current_node": "troubleshooting",
#             "troubleshooting_needs_escalation": True,
#             "troubleshooting_escalation_reason": "step_not_found",
#         }
    
#     # Get recent messages for context
#     recent_ts_messages = [m for m in messages if m.get("node") == "troubleshooting"][-10:]
    
#     # Get already checked items
#     checked_items = ts_state.get("checked_items", {})
#     logger.info(f"Already checked items: {checked_items}")
    
#     # Analyze response with conversation context, problem_context, AND checked_items
#     analysis = analyze_user_response(
#         current_step, 
#         user_response, 
#         recent_ts_messages,
#         context_summary,
#         checked_items  # Pass checked items to prevent repeating
#     )
    
#     # Merge newly extracted checks into checked_items
#     if analysis.extracted_checks:
#         checked_items = {**checked_items, **analysis.extracted_checks}
#         logger.info(f"Updated checked items: {checked_items}")
    
#     logger.info(f"Analysis: branch={analysis.selected_branch}, needs_substep={analysis.needs_next_substep}, clarify={analysis.needs_clarification}")
    
#     if analysis.needs_clarification:
#         message = add_message(
#             role="assistant",
#             content=analysis.clarification_question,
#             node="troubleshooting"
#         )
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_checked_items": checked_items,
#         }
    
#     if analysis.needs_next_substep and analysis.next_substep_instruction:
#         logger.info(f"Guiding to next substep within step {ts_state['current_step']}")
#         message = add_message(
#             role="assistant",
#             content=analysis.next_substep_instruction,
#             node="troubleshooting"
#         )
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_checked_items": checked_items,
#         }
    
#     # Determine next action based on selected branch
#     branches = current_step.get("branches", {})
#     selected_branch_data = branches.get(analysis.selected_branch, {})
    
#     action = selected_branch_data.get("action")
#     next_step_id = selected_branch_data.get("next_step")
#     branch_message = selected_branch_data.get("message", "")
    
#     # Update completed steps
#     completed = ts_state.get("completed_steps", []) + [ts_state["current_step"]]
    
#     if action == "resolved":
#         logger.info("Problem resolved! → create_ticket (silent)")
#         message = add_message(
#             role="assistant",
#             content=f"{branch_message}\n\nDžiaugiuosi, kad pavyko išspręsti problemą!",
#             node="troubleshooting"
#         )
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "problem_resolved": True,
#             "troubleshooting_completed_steps": completed,
#             "troubleshooting_checked_items": checked_items,
#         }
    
#     elif action == "escalate":
#         logger.info(f"Escalating: {selected_branch_data.get('reason')} → create_ticket")
#         message = add_message(
#             role="assistant",
#             content=f"{branch_message}\n\nSukursiu techninės pagalbos užklausą.",
#             node="troubleshooting"
#         )
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_needs_escalation": True,
#             "troubleshooting_escalation_reason": selected_branch_data.get("reason"),
#             "troubleshooting_completed_steps": completed,
#             "troubleshooting_checked_items": checked_items,
#         }
    
#     elif next_step_id:
#         next_step = scenario.get_step(next_step_id)
        
#         if not next_step:
#             logger.error(f"Next step not found: {next_step_id}")
#             message = add_message(
#                 role="assistant",
#                 content="Įvyko klaida scenarijuje. Sukursiu techninės pagalbos užklausą.",
#                 node="troubleshooting"
#             )
#             return {
#                 "messages": [message],
#                 "current_node": "troubleshooting",
#                 "troubleshooting_needs_escalation": True,
#                 "troubleshooting_escalation_reason": "next_step_not_found",
#                 "troubleshooting_completed_steps": completed,
#                 "troubleshooting_checked_items": checked_items,
#             }
        
#         instruction_text = format_step_instruction(next_step, customer_name)
#         message = add_message(
#             role="assistant",
#             content=f"{branch_message}\n\n**{next_step.get('title')}**\n\n{instruction_text}",
#             node="troubleshooting"
#         )
        
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_current_step": next_step_id,
#             "troubleshooting_completed_steps": completed,
#             "troubleshooting_checked_items": checked_items,
#         }
    
#     else:
#         logger.warning(f"No action or next_step for branch: {analysis.selected_branch}")
#         message = add_message(
#             role="assistant",
#             content="Nepavyko automatiškai išspręsti problemos. Sukursiu techninės pagalbos užklausą.",
#             node="troubleshooting"
#         )
#         return {
#             "messages": [message],
#             "current_node": "troubleshooting",
#             "troubleshooting_needs_escalation": True,
#             "troubleshooting_escalation_reason": "no_matching_branch",
#             "troubleshooting_completed_steps": completed,
#             "troubleshooting_checked_items": checked_items,
#         }


# # =============================================================================
# # ROUTER FUNCTION
# # =============================================================================

# def troubleshooting_router(state) -> str:
#     """
#     Route after troubleshooting.
    
#     Returns:
#         - "create_ticket" → create ticket (both resolved and escalation)
#         - "end" → wait for user response
#     """
#     problem_resolved = _get_attr(state, "problem_resolved", False) 
#     needs_escalation = _get_attr(state, "troubleshooting_needs_escalation", False)
    
#     logger.info(f"Router: resolved={problem_resolved}, escalation={needs_escalation}")
    
#     if problem_resolved:
#         logger.info("→ create_ticket (resolved)")
#         return "create_ticket"
    
#     if needs_escalation:
#         logger.info("→ create_ticket (escalation)")
#         return "create_ticket"
    
#     logger.info("→ end (waiting for user)")
#     return "end"
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
from src.rag.retriever import get_retriever

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


def get_smart_scenario_id(problem_type: str, problem_context: dict, diagnostic_results: dict = None) -> str:
    """
    Select the most appropriate scenario based on context.
    
    Smart routing:
    - Single device problem → internet_single_device (device-first approach)
    - All devices problem → internet_no_connection (router-first approach)
    """
    if problem_type != "internet":
        # For non-internet problems, use default scenarios
        default_scenarios = {
            "tv": "tv_no_signal",
            "phone": "internet_no_connection",  # fallback
            "other": "internet_no_connection",
        }
        return default_scenarios.get(problem_type, "internet_no_connection")
    
    # For internet problems, check scope to determine best scenario
    if problem_context:
        scope = str(problem_context.get("scope", "")).lower()
        
        # Single device keywords - use device-first scenario
        single_device_keywords = [
            "telefonas", "telefone", "phone", 
            "vienas", "viename", "tik vienas",
            "laptop", "kompiuteris", "kompiuteryje",
            "tablet", "planšetė"
        ]
        
        if any(kw in scope for kw in single_device_keywords):
            # Try to use single device scenario if available
            # Will fallback to internet_no_connection if scenario not loaded
            logger.info(f"Smart routing: Single device detected ('{scope}') → internet_single_device")
            return "internet_single_device"
        
        # All devices affected - router-first approach
        all_devices_keywords = ["visi", "visur", "visuose", "all", "viskas"]
        if any(kw in scope for kw in all_devices_keywords):
            logger.info(f"Smart routing: All devices affected ('{scope}') → internet_no_connection")
            return "internet_no_connection"
    
    # Default fallback
    return "internet_no_connection"


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
    
    default_scenarios = {
        "internet": "internet_no_connection",
        "tv": "tv_no_signal",
        "phone": "internet_no_connection",
        "other": "internet_no_connection",
    }
    return default_scenarios.get(actual_type, "internet_no_connection")


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
        scenario_id = get_smart_scenario_id(problem_type, problem_context, diagnostic_results)
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
