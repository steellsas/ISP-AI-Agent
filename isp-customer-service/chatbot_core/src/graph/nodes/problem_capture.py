
# # """
# # Problem Capture Node v2.1 - Extracts and qualifies customer problem

# # Uses LLM to:
# # 1. Classify problem type (internet/tv/phone/billing/other)
# # 2. Extract ALL known facts from user messages
# # 3. Calculate context completeness score
# # 4. Ask qualifying questions if needed (max 3)
# # 5. Proceed when context >= threshold OR max questions reached

# # Configuration-driven:
# # - Problem types, questions, weights → config/problem_types.yaml
# # - Messages → config/messages.yaml  
# # - Prompts → prompts/problem_capture/*.txt
# # """

# # import sys
# # import logging
# # from pathlib import Path
# # from pydantic import BaseModel
# # from typing import Literal, Any

# # # Try to import from shared module
# # try:
# #     shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
# #     if str(shared_path) not in sys.path:
# #         sys.path.insert(0, str(shared_path))
# #     from utils import get_logger
# # except ImportError:
# #     logging.basicConfig(level=logging.INFO)
# #     def get_logger(name):
# #         return logging.getLogger(name)

# # # Services
# # from src.services.llm import llm_json_completion
# # from src.services.config_loader import (
# #     get_problem_type_config,
# #     get_all_problem_types,
# #     get_context_fields,
# #     get_context_threshold,
# #     get_max_questions,
# #     get_question_priority,
# #     get_skip_phrases,
# #     get_unknown_phrases,
# #     classify_problem_type_by_keywords,
# #     calculate_context_score,
# #     get_next_question,
# #     get_message,
# #     format_problem_types_list,
# #     format_context_fields_description,
# #     format_known_facts_summary,
# #     format_question_priority,
# # )
# # from src.services.prompt_loader import (
# #     get_prompt,
# #     get_system_persona,
# #     build_conversation_history,
# # )

# # # State
# # from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

# # logger = get_logger(__name__)


# # # =============================================================================
# # # STRUCTURED OUTPUT SCHEMA
# # # =============================================================================

# # class ProblemAnalysis(BaseModel):
# #     """LLM response schema for problem analysis v2.1."""
    
# #     # Classification
# #     problem_type: Literal["internet", "tv", "phone", "billing", "other"]
# #     problem_summary: str
    
# #     # Extracted facts (what we now know)
# #     known_facts: dict[str, Any]  # field_name -> value or None
    
# #     # Context completeness
# #     context_score: int  # 0-100
    
# #     # Decision
# #     ready_to_proceed: bool
    
# #     # Next question (if not ready)
# #     next_question: str | None = None
# #     question_target: str | None = None  # Which field we're asking about
# #     simpler_alternative: str | None = None  # If user doesn't know
    
# #     # User intent detection
# #     user_said_unknown: bool = False  # User said "nežinau"
# #     user_wants_to_skip: bool = False  # User said "tiesiog padėkite"


# # # =============================================================================
# # # HELPER FUNCTIONS
# # # =============================================================================

# # def _detect_user_intent(user_message: str) -> dict:
# #     """
# #     Detect if user wants to skip or says they don't know.
    
# #     Returns:
# #         dict with 'wants_skip' and 'says_unknown' booleans
# #     """
# #     message_lower = user_message.lower()
    
# #     skip_phrases = get_skip_phrases()
# #     unknown_phrases = get_unknown_phrases()
    
# #     wants_skip = any(phrase in message_lower for phrase in skip_phrases)
# #     says_unknown = any(phrase in message_lower for phrase in unknown_phrases)
    
# #     return {
# #         "wants_skip": wants_skip,
# #         "says_unknown": says_unknown,
# #     }


# # def _merge_known_facts(existing: dict, new_facts: dict) -> dict:
# #     """
# #     Merge new facts into existing, preserving non-null values.
    
# #     Args:
# #         existing: Current known facts
# #         new_facts: Newly extracted facts
        
# #     Returns:
# #         Merged facts dict
# #     """
# #     merged = existing.copy()
    
# #     for key, value in new_facts.items():
# #         # Only update if new value is not None
# #         if value is not None:
# #             merged[key] = value
# #         # Keep existing value if new is None
# #         elif key not in merged:
# #             merged[key] = None
    
# #     return merged


# # def _build_analysis_prompt(
# #     user_message: str,
# #     problem_type: str,
# #     known_facts: dict,
# #     questions_asked: int,
# #     conversation_history: list[dict],
# # ) -> str:
# #     """
# #     Build the full analysis prompt with all context.
    
# #     Args:
# #         user_message: Current user message
# #         problem_type: Current/detected problem type
# #         known_facts: Currently known facts
# #         questions_asked: Number of questions asked
# #         conversation_history: Previous messages
        
# #     Returns:
# #         Complete formatted prompt
# #     """
# #     # Get config values
# #     context_threshold = get_context_threshold(problem_type)
# #     max_questions = get_max_questions(problem_type)
    
# #     # Format prompt components
# #     problem_types_list = format_problem_types_list()
# #     context_fields_desc = format_context_fields_description(problem_type)
# #     known_facts_summary = format_known_facts_summary(known_facts)
# #     question_priority = format_question_priority(problem_type)
# #     history_text = build_conversation_history(conversation_history)
    
# #     # Get and format prompt template
# #     prompt = get_prompt(
# #         "problem_capture",
# #         "analyze_problem",
# #         user_message=user_message,
# #         current_problem_type=problem_type,
# #         problem_types_list=problem_types_list,
# #         context_fields_description=context_fields_desc,
# #         known_facts_summary=known_facts_summary,
# #         questions_asked=questions_asked,
# #         max_questions=max_questions,
# #         conversation_history=history_text,
# #         question_priority=question_priority,
# #         context_threshold=context_threshold,
# #     )
    
# #     return prompt


# # def _translate_problem_type(problem_type: str | None) -> str:
# #     """Translate problem type to Lithuanian genitive case."""
# #     translations = {
# #         "internet": "interneto",
# #         "tv": "televizijos", 
# #         "phone": "telefono",
# #         "billing": "sąskaitos/mokėjimo",
# #         "other": "paslaugos"
# #     }
# #     return translations.get(problem_type, "paslaugos")


# # # =============================================================================
# # # MAIN NODE FUNCTION
# # # =============================================================================

# # def problem_capture_node(state) -> dict:
# #     """
# #     Problem capture node v2.1 - analyzes and qualifies customer problem.
    
# #     Flow:
# #     1. Get user message
# #     2. Detect problem type (from keywords or LLM)
# #     3. Extract known facts from conversation
# #     4. Calculate context score
# #     5. If score >= threshold OR questions >= max → proceed
# #     6. Otherwise → ask next qualifying question
    
# #     Args:
# #         state: Current conversation state
        
# #     Returns:
# #         State update dict
# #     """
# #     logger.info("=== Problem Capture Node v2.1 ===")
    
# #     # Get current state values
# #     user_message = get_last_user_message(state)
# #     current_problem_type = _get_attr(state, "problem_type")
# #     current_context = _get_attr(state, "problem_context", {})
# #     questions_asked = _get_attr(state, "qualifying_questions_asked", 0)
# #     qualifying_answers = _get_attr(state, "qualifying_answers", [])
    
# #     logger.info(f"User message: {user_message}")
# #     logger.info(f"Current type: {current_problem_type}, questions asked: {questions_asked}")
    
# #     if not user_message:
# #         logger.warning("No user message found")
# #         return {"current_node": "problem_capture"}
    
# #     # === Step 1: Detect user intent (skip/unknown) ===
# #     user_intent = _detect_user_intent(user_message)
    
# #     if user_intent["wants_skip"]:
# #         logger.info("User wants to skip qualifying questions")
# #         # Acknowledge and proceed with what we have
# #         skip_msg = get_message("problem_capture", "skip_acknowledged")
# #         transition_msg = get_message("problem_capture", "transitioning_to_lookup")
        
# #         message = add_message(
# #             role="assistant",
# #             content=f"{skip_msg} {transition_msg}",
# #             node="problem_capture"
# #         )
        
# #         return {
# #             "messages": [message],
# #             "current_node": "problem_capture",
# #             "problem_capture_complete": True,
# #             "problem_type": current_problem_type or "other",
# #             "problem_description": user_message,
# #         }
    
# #     # === Step 2: Initial problem type detection (if not set) ===
# #     if not current_problem_type:
# #         detected_type = classify_problem_type_by_keywords(user_message)
# #         if detected_type:
# #             current_problem_type = detected_type
# #             logger.info(f"Detected problem type from keywords: {detected_type}")
# #         else:
# #             current_problem_type = "other"  # Will be refined by LLM
    
# #     # === Step 3: Build prompt and call LLM ===
# #     conversation_history = _get_messages(state)
    
# #     prompt = _build_analysis_prompt(
# #         user_message=user_message,
# #         problem_type=current_problem_type,
# #         known_facts=current_context,
# #         questions_asked=questions_asked,
# #         conversation_history=conversation_history,
# #     )
    
# #     # Get system persona
# #     system_prompt = get_system_persona()
    
# #     messages = [
# #         {"role": "system", "content": system_prompt},
# #         {"role": "user", "content": prompt}
# #     ]
    
# #     try:
# #         response = llm_json_completion(
# #             messages=messages,
# #             temperature=0.3,
# #             max_tokens=500
# #         )
        
# #         analysis = ProblemAnalysis(**response)
# #         logger.info(f"Analysis: type={analysis.problem_type}, score={analysis.context_score}, ready={analysis.ready_to_proceed}")
        
# #     except Exception as e:
# #         logger.error(f"LLM error: {e}")
        
# #         # Track error count
# #         current_error_count = _get_attr(state, "llm_error_count", 0) + 1
        
# #         if current_error_count >= 3:
# #             error_message = add_message(
# #                 role="assistant",
# #                 content=get_message("errors", "llm_error"),
# #                 node="problem_capture"
# #             )
# #             return {
# #                 "messages": [error_message],
# #                 "current_node": "problem_capture",
# #                 "last_error": str(e),
# #                 "llm_error_count": current_error_count,
# #                 "conversation_ended": True,
# #             }
        
# #         # Fallback - ask generic question
# #         fallback_message = add_message(
# #             role="assistant",
# #             content=get_message("errors", "not_understood"),
# #             node="problem_capture"
# #         )
# #         return {
# #             "messages": [fallback_message],
# #             "current_node": "problem_capture",
# #             "last_error": str(e),
# #             "llm_error_count": current_error_count,
# #         }
    
# #     # === Step 4: Update known facts ===
# #     updated_facts = _merge_known_facts(current_context, analysis.known_facts)
# #     updated_facts["context_score"] = analysis.context_score
    
# #     # Record Q&A if this was an answer to a question
# #     if questions_asked > 0:
# #         last_question = qualifying_answers[-1] if qualifying_answers else {}
# #         updated_answers = qualifying_answers + [{
# #             "question": last_question.get("next_question", ""),
# #             "answer": user_message,
# #             "target_field": last_question.get("target_field", ""),
# #             "understood": not analysis.user_said_unknown,
# #         }]
# #     else:
# #         updated_answers = qualifying_answers
    
# #     # === Step 5: Determine if ready to proceed ===
# #     threshold = get_context_threshold(analysis.problem_type)
# #     max_q = get_max_questions(analysis.problem_type)
    
# #     should_proceed = (
# #         analysis.ready_to_proceed or
# #         analysis.context_score >= threshold or
# #         questions_asked >= max_q or
# #         analysis.user_wants_to_skip
# #     )
    
# #     logger.info(f"Should proceed: {should_proceed} (score={analysis.context_score}/{threshold}, q={questions_asked}/{max_q})")
    
# #     if should_proceed:
# #         # === PROCEED TO NEXT NODE ===
# #         logger.info("Context sufficient - proceeding to phone_lookup")
        
# #         # Build confirmation message
# #         acknowledgment = get_message(
# #             "problem_capture", 
# #             "initial_acknowledgment", 
# #             problem_type=analysis.problem_type
# #         )
        
# #         if analysis.problem_summary:
# #             # Use summary if available
# #             confirmation = f"{acknowledgment} {analysis.problem_summary}."
# #         else:
# #             confirmation = acknowledgment
        
# #         transition = get_message("problem_capture", "transitioning_to_lookup")
# #         full_message = f"{confirmation} {transition}"
        
# #         message = add_message(
# #             role="assistant",
# #             content=full_message,
# #             node="problem_capture"
# #         )
        
# #         return {
# #             "messages": [message],
# #             "current_node": "problem_capture",
# #             "problem_type": analysis.problem_type,
# #             "problem_description": analysis.problem_summary,
# #             "problem_context": updated_facts,
# #             "problem_capture_complete": True,
# #             "qualifying_questions_asked": questions_asked,
# #             "qualifying_answers": updated_answers,
# #         }
    
# #     else:
# #         # === ASK NEXT QUESTION ===
# #         logger.info(f"Need more context - asking question #{questions_asked + 1}")
        
# #         # Determine which question to ask
# #         if analysis.user_said_unknown and analysis.simpler_alternative:
# #             # User didn't know - ask simpler version
# #             question = analysis.simpler_alternative
# #             prefix = get_message("problem_capture", "question_prefix", key="after_unknown")
# #             question_text = f"{prefix} {question}" if prefix else question
# #         else:
# #             # Use LLM's suggested question
# #             question_text = analysis.next_question
        
# #         # If no question from LLM, get from config
# #         if not question_text:
# #             next_q = get_next_question(
# #                 analysis.problem_type, 
# #                 updated_facts,
# #                 use_simpler=analysis.user_said_unknown
# #             )
# #             if next_q:
# #                 question_text = next_q["question"]
# #                 analysis.question_target = next_q["field"]
        
# #         # Fallback question
# #         if not question_text:
# #             question_text = "Ar galėtumėte plačiau papasakoti apie problemą?"
        
# #         # First question - add acknowledgment
# #         if questions_asked == 0:
# #             acknowledgment = get_message(
# #                 "problem_capture",
# #                 "initial_acknowledgment",
# #                 problem_type=analysis.problem_type
# #             )
# #             full_message = f"{acknowledgment} {question_text}"
# #         else:
# #             full_message = question_text
        
# #         message = add_message(
# #             role="assistant",
# #             content=full_message,
# #             node="problem_capture"
# #         )
        
# #         # Track for next iteration
# #         new_answers = updated_answers + [{
# #             "next_question": question_text,
# #             "target_field": analysis.question_target,
# #         }]
        
# #         return {
# #             "messages": [message],
# #             "current_node": "problem_capture",
# #             "problem_type": analysis.problem_type,
# #             "problem_context": updated_facts,
# #             "qualifying_questions_asked": questions_asked + 1,
# #             "qualifying_answers": new_answers,
# #         }


# # # =============================================================================
# # # ROUTER FUNCTION
# # # =============================================================================

# # def problem_capture_router(state) -> str:
# #     """
# #     Route after problem capture.
    
# #     Returns:
# #         - "end" → wait for user input (asked question or error)
# #         - "phone_lookup" → problem qualified, continue workflow
# #     """
# #     # Check if conversation ended (due to error)
# #     if _get_attr(state, "conversation_ended", False):
# #         logger.info("Conversation ended → END")
# #         return "end"
    
# #     # Check if problem capture is complete
# #     if _get_attr(state, "problem_capture_complete", False):
# #         problem_type = _get_attr(state, "problem_type")
# #         context_score = _get_attr(state, "problem_context", {}).get("context_score", 0)
# #         logger.info(f"Problem capture complete: {problem_type} (score: {context_score}) → phone_lookup")
# #         return "phone_lookup"
    
# #     # Check legacy fields for backward compatibility
# #     problem_type = _get_attr(state, "problem_type")
# #     problem_description = _get_attr(state, "problem_description")
    
# #     if problem_type and problem_description:
# #         logger.info(f"Problem clear (legacy): {problem_type} → phone_lookup")
# #         return "phone_lookup"
    
# #     # Asked a question - wait for user response
# #     logger.info("Waiting for user response → END")
# #     return "end"


# """
# Problem Capture Node v2.2 - Extracts and qualifies customer problem

# Uses LLM to:
# 1. Classify problem type (internet/tv/phone/billing/other)
# 2. Extract ALL known facts from user messages
# 3. Calculate context completeness score
# 4. Ask qualifying questions if needed (max 3)
# 5. Proceed when context >= threshold OR max questions reached

# Configuration-driven:
# - Problem types, questions, weights → config/problem_types.yaml
# - Messages → i18n/{lang}/messages.yaml
# - Prompts → prompts/problem_capture/*.txt

# Supports multiple languages via translation service.
# """

# import logging
# from typing import Any, Literal
# from pydantic import BaseModel

# # Services
# from src.services.llm import llm_json_completion
# from src.services.language_service import get_language, get_language_name
# from src.services.translation_service import t, t_list
# from src.services.config_loader import (
#     get_problem_type_config,
#     get_all_problem_types,
#     get_context_fields,
#     get_context_threshold,
#     get_max_questions,
#     get_question_priority,
#     classify_problem_type_by_keywords,
#     calculate_context_score,
#     get_next_question,
#     format_problem_types_list,
#     format_context_fields_description,
#     format_known_facts_summary,
#     format_question_priority,
# )
# from src.services.prompt_loader import (
#     get_prompt,
#     get_system_persona,
#     build_conversation_history,
# )

# from src.services.language_service import (
#     sync_language_from_state
# )

# # State
# from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

# logger = logging.getLogger(__name__)


# # =============================================================================
# # STRUCTURED OUTPUT SCHEMA
# # =============================================================================

# class ProblemAnalysis(BaseModel):
#     """LLM response schema for problem analysis."""
    
#     # Classification
#     problem_type: Literal["internet", "tv", "billing", "other"]
#     problem_summary: str
    
#     # Extracted facts (what we now know)
#     known_facts: dict[str, Any]  # field_name -> value or None
    
#     # Context completeness
#     context_score: int  # 0-100
    
#     # Decision
#     ready_to_proceed: bool
    
#     # Next question (if not ready)
#     next_question: str | None = None
#     question_target: str | None = None  # Which field we're asking about
#     simpler_alternative: str | None = None  # If user doesn't know
    
#     # User intent detection
#     user_said_unknown: bool = False  # User said "nežinau"
#     user_wants_to_skip: bool = False  # User said "tiesiog padėkite"


# # =============================================================================
# # HELPER FUNCTIONS
# # =============================================================================

# def _detect_user_intent(user_message: str) -> dict:
#     """
#     Detect if user wants to skip or says they don't know.
    
#     Uses phrases from translation service.
    
#     Returns:
#         dict with 'wants_skip' and 'says_unknown' booleans
#     """
#     message_lower = user_message.lower()
    
#     # Get phrases from translation
#     skip_phrases = t_list("skip")
#     unknown_phrases = t_list("help_request.confused") + ["nežinau", "nezinau", "i don't know"]
    
#     wants_skip = any(phrase in message_lower for phrase in skip_phrases)
#     says_unknown = any(phrase in message_lower for phrase in unknown_phrases)
    
#     return {
#         "wants_skip": wants_skip,
#         "says_unknown": says_unknown,
#     }


# def _merge_known_facts(existing: dict, new_facts: dict) -> dict:
#     """
#     Merge new facts into existing, preserving non-null values.
    
#     Args:
#         existing: Current known facts
#         new_facts: Newly extracted facts
        
#     Returns:
#         Merged facts dict
#     """
#     merged = existing.copy()
    
#     for key, value in new_facts.items():
#         # Only update if new value is not None
#         if value is not None:
#             merged[key] = value
#         # Keep existing value if new is None
#         elif key not in merged:
#             merged[key] = None
    
#     return merged


# def _build_analysis_prompt(
#     user_message: str,
#     problem_type: str,
#     known_facts: dict,
#     questions_asked: int,
#     conversation_history: list[dict],
# ) -> str:
#     """
#     Build the full analysis prompt with all context.
    
#     Args:
#         user_message: Current user message
#         problem_type: Current/detected problem type
#         known_facts: Currently known facts
#         questions_asked: Number of questions asked
#         conversation_history: Previous messages
        
#     Returns:
#         Complete formatted prompt
#     """
#     # Get config values
#     context_threshold = get_context_threshold(problem_type)
#     max_questions = get_max_questions(problem_type)
#     output_language = get_language_name()
    
#     # Format prompt components
#     problem_types_list = format_problem_types_list()
#     context_fields_desc = format_context_fields_description(problem_type)
#     known_facts_summary = format_known_facts_summary(known_facts)
#     question_priority = format_question_priority(problem_type)
#     history_text = build_conversation_history(conversation_history)
    
#     # Get and format prompt template
#     prompt = get_prompt(
#         "problem_capture",
#         "analyze_problem",
#         user_message=user_message,
#         current_problem_type=problem_type,
#         problem_types_list=problem_types_list,
#         context_fields_description=context_fields_desc,
#         known_facts_summary=known_facts_summary,
#         questions_asked=questions_asked,
#         max_questions=max_questions,
#         conversation_history=history_text,
#         question_priority=question_priority,
#         context_threshold=context_threshold,
#         output_language=output_language,
#     )
    
#     return prompt


# def _get_acknowledgment(problem_type: str) -> str:
#     """
#     Get acknowledgment message for problem type.
    
#     Args:
#         problem_type: Detected problem type
        
#     Returns:
#         Translated acknowledgment message
#     """
#     # Try specific type first
#     message = t(f"problem_capture.acknowledgment.{problem_type}")
    
#     # Fallback to default
#     if message.startswith("["):  # Translation not found
#         message = t("problem_capture.acknowledgment.default")
    
#     return message


# # =============================================================================
# # MAIN NODE FUNCTION
# # =============================================================================

# def problem_capture_node(state: Any) -> dict:
#     """
#     Problem capture node - analyzes and qualifies customer problem.
    
#     Flow:
#     1. Get user message
#     2. Detect problem type (from keywords or LLM)
#     3. Extract known facts from conversation
#     4. Calculate context score
#     5. If score >= threshold OR questions >= max → proceed
#     6. Otherwise → ask next qualifying question
    
#     Args:
#         state: Current conversation state
        
#     Returns:
#         State update dict
#     """
#     conversation_id = _get_attr(state, "conversation_id", "unknown")
#     lang = sync_language_from_state(state)
    
#     logger.info(f"[{conversation_id}] Node started | language={lang}")
#     logger.info(f"[{conversation_id}] Problem capture node started")
    
#     # Get current state values
#     user_message = get_last_user_message(state)
#     current_problem_type = _get_attr(state, "problem_type")
#     current_context = _get_attr(state, "problem_context", {})
#     questions_asked = _get_attr(state, "qualifying_questions_asked", 0)
#     qualifying_answers = _get_attr(state, "qualifying_answers", [])
    
#     logger.debug(
#         f"[{conversation_id}] State: type={current_problem_type}, "
#         f"questions={questions_asked}, context_keys={list(current_context.keys())}"
#     )
    
#     # Handle missing message
#     if not user_message:
#         logger.warning(f"[{conversation_id}] No user message")
#         return {
#             "current_node": "problem_capture",
#             "problem_type": current_problem_type or "other",
#             "problem_description": user_message,
#         }
    
#     # === Step 1: Detect user intent ===
#     intent = _detect_user_intent(user_message)
    
#     if intent["wants_skip"]:
#         logger.info(f"[{conversation_id}] User wants to skip qualifying questions")
    
#     # === Step 2: Initial problem type detection (if not set) ===
#     if not current_problem_type:
#         detected_type = classify_problem_type_by_keywords(user_message)
#         if detected_type:
#             current_problem_type = detected_type
#             logger.info(f"[{conversation_id}] Detected problem type from keywords: {detected_type}")
#         else:
#             current_problem_type = "other"  # Will be refined by LLM
    
#     # === Step 3: Build prompt and call LLM ===
#     conversation_history = _get_messages(state)
    
#     prompt = _build_analysis_prompt(
#         user_message=user_message,
#         problem_type=current_problem_type,
#         known_facts=current_context,
#         questions_asked=questions_asked,
#         conversation_history=conversation_history,
#     )
    
#     # Get system persona
#     system_prompt = get_system_persona()
    
#     messages = [
#         {"role": "system", "content": system_prompt},
#         {"role": "user", "content": prompt}
#     ]
    
#     try:
#         response = llm_json_completion(
#             messages=messages,
#             temperature=0.3,
#             max_tokens=500
#         )
        
#         analysis = ProblemAnalysis(**response)
        
#         logger.info(
#             f"[{conversation_id}] Analysis: type={analysis.problem_type}, "
#             f"score={analysis.context_score}, ready={analysis.ready_to_proceed}"
#         )
        
#     except Exception as e:
#         logger.error(f"[{conversation_id}] LLM error: {e}", exc_info=True)
        
#         # Track error count
#         current_error_count = _get_attr(state, "llm_error_count", 0) + 1
        
#         if current_error_count >= 3:
#             error_message = add_message(
#                 role="assistant",
#                 content=t("errors.llm_error"),
#                 node="problem_capture"
#             )
#             return {
#                 "messages": [error_message],
#                 "current_node": "problem_capture",
#                 "last_error": str(e),
#                 "llm_error_count": current_error_count,
#                 "conversation_ended": True,
#             }
        
#         # Fallback - ask generic question
#         fallback_message = add_message(
#             role="assistant",
#             content=t("errors.not_understood"),
#             node="problem_capture"
#         )
#         return {
#             "messages": [fallback_message],
#             "current_node": "problem_capture",
#             "last_error": str(e),
#             "llm_error_count": current_error_count,
#         }
    
#     # === Step 4: Update known facts ===
#     updated_facts = _merge_known_facts(current_context, analysis.known_facts)
#     updated_facts["context_score"] = analysis.context_score
    
#     # Record Q&A if this was an answer to a question
#     if questions_asked > 0:
#         last_question = qualifying_answers[-1] if qualifying_answers else {}
#         updated_answers = qualifying_answers + [{
#             "question": last_question.get("next_question", ""),
#             "answer": user_message,
#             "target_field": last_question.get("target_field", ""),
#             "understood": not analysis.user_said_unknown,
#         }]
#     else:
#         updated_answers = qualifying_answers
    
#     # === Step 5: Determine if ready to proceed ===
#     threshold = get_context_threshold(analysis.problem_type)
#     max_q = get_max_questions(analysis.problem_type)
    
#     should_proceed = (
#         analysis.ready_to_proceed or
#         analysis.context_score >= threshold or
#         questions_asked >= max_q or
#         analysis.user_wants_to_skip or
#         intent["wants_skip"]
#     )
    
#     logger.info(
#         f"[{conversation_id}] Should proceed: {should_proceed} "
#         f"(score={analysis.context_score}/{threshold}, q={questions_asked}/{max_q})"
#     )
    
#     if should_proceed:
#         # === PROCEED TO NEXT NODE ===
#         logger.info(f"[{conversation_id}] Context sufficient - proceeding to phone_lookup")
        
#         # Build confirmation message
#         acknowledgment = _get_acknowledgment(analysis.problem_type)
        
#         if analysis.problem_summary:
#             confirmation = f"{acknowledgment} {analysis.problem_summary}."
#         else:
#             confirmation = acknowledgment
        
#         transition = t("problem_capture.transitioning")
#         full_message = f"{confirmation} {transition}"
        
#         message = add_message(
#             role="assistant",
#             content=full_message,
#             node="problem_capture"
#         )
        
#         logger.info(f"[{conversation_id}] Problem capture complete | type={analysis.problem_type} | lang={get_language()}")
        
#         return {
#             "messages": [message],
#             "current_node": "problem_capture",
#             "problem_type": analysis.problem_type,
#             "problem_description": analysis.problem_summary,
#             "problem_context": updated_facts,
#             "problem_capture_complete": True,
#             "qualifying_questions_asked": questions_asked,
#             "qualifying_answers": updated_answers,
#         }
    
#     else:
#         # === ASK NEXT QUESTION ===
#         logger.info(f"[{conversation_id}] Need more context - asking question #{questions_asked + 1}")
        
#         # Determine which question to ask
#         if analysis.user_said_unknown and analysis.simpler_alternative:
#             # User didn't know - ask simpler version
#             question_text = t("problem_capture.user_unknown") + " " + analysis.simpler_alternative
#         else:
#             # Use LLM's suggested question
#             question_text = analysis.next_question
        
#         # If no question from LLM, get from config
#         if not question_text:
#             next_q = get_next_question(
#                 analysis.problem_type, 
#                 updated_facts,
#                 use_simpler=analysis.user_said_unknown
#             )
#             if next_q:
#                 question_text = next_q["question"]
#                 analysis.question_target = next_q["field"]
        
#         # Fallback question
#         if not question_text:
#             question_text = t("problem_capture.ask_more_details")
        
#         # First question - add acknowledgment
#         if questions_asked == 0:
#             acknowledgment = _get_acknowledgment(analysis.problem_type)
#             full_message = f"{acknowledgment} {question_text}"
#         else:
#             full_message = question_text
        
#         message = add_message(
#             role="assistant",
#             content=full_message,
#             node="problem_capture"
#         )
        
#         # Track for next iteration
#         new_answers = updated_answers + [{
#             "next_question": question_text,
#             "target_field": analysis.question_target,
#         }]
        
#         return {
#             "messages": [message],
#             "current_node": "problem_capture",
#             "problem_type": analysis.problem_type,
#             "problem_context": updated_facts,
#             "qualifying_questions_asked": questions_asked + 1,
#             "qualifying_answers": new_answers,
#         }


# # =============================================================================
# # ROUTER FUNCTION
# # =============================================================================

# def problem_capture_router(state: Any) -> str:
#     """
#     Route after problem capture.
    
#     Returns:
#         - "end" → wait for user input (asked question or error)
#         - "phone_lookup" → problem qualified, continue workflow
#     """
#     conversation_id = _get_attr(state, "conversation_id", "unknown")
    
#     # Check if conversation ended (due to error)
#     if _get_attr(state, "conversation_ended", False):
#         logger.info(f"[{conversation_id}] Router → end (conversation ended)")
#         return "end"
    
#     # Check if problem capture is complete
#     if _get_attr(state, "problem_capture_complete", False):
#         problem_type = _get_attr(state, "problem_type")
#         context_score = _get_attr(state, "problem_context", {}).get("context_score", 0)
#         logger.info(f"[{conversation_id}] Router → phone_lookup (complete: {problem_type}, score: {context_score})")
#         return "phone_lookup"
    
#     # Check legacy fields for backward compatibility
#     problem_type = _get_attr(state, "problem_type")
#     problem_description = _get_attr(state, "problem_description")
    
#     if problem_type and problem_description:
#         logger.info(f"[{conversation_id}] Router → phone_lookup (legacy: {problem_type})")
#         return "phone_lookup"
    
#     # Asked a question - wait for user response
#     logger.info(f"[{conversation_id}] Router → end (waiting for user)")
#     return "end"


"""
Problem Capture Node v2.2 - Extracts and qualifies customer problem

Uses LLM to:
1. Classify problem type (internet/tv/phone/billing/other)
2. Extract ALL known facts from user messages
3. Calculate context completeness score
4. Ask qualifying questions if needed (max 3)
5. Proceed when context >= threshold OR max questions reached

Configuration-driven:
- Problem types, questions, weights → config/problem_types.yaml
- Messages → i18n/{lang}/messages.yaml
- Prompts → prompts/problem_capture/*.txt

Supports multiple languages via translation service.
"""

import logging
from typing import Any, Literal
from pydantic import BaseModel

# Services
from src.services.llm import llm_json_completion
from src.services.language_service import (
    get_language, 
    get_language_name,
    sync_language_from_state,
)
from src.services.translation_service import t, t_list
from src.services.config_loader import (
    get_problem_type_config,
    get_all_problem_types,
    get_context_fields,
    get_context_threshold,
    get_max_questions,
    get_question_priority,
    classify_problem_type_by_keywords,
    calculate_context_score,
    get_next_question,
    format_problem_types_list,
    format_context_fields_description,
    format_known_facts_summary,
    format_question_priority,
)
from src.services.prompt_loader import (
    get_prompt,
    get_system_persona,
    build_conversation_history,
)

# State
from src.graph.state import add_message, get_last_user_message, _get_messages, _get_attr

logger = logging.getLogger(__name__)


# =============================================================================
# STRUCTURED OUTPUT SCHEMA
# =============================================================================

class ProblemAnalysis(BaseModel):
    """LLM response schema for problem analysis."""
    
    # Classification
    problem_type: Literal["internet", "tv", "phone", "billing", "other"]
    problem_summary: str
    
    # Extracted facts (what we now know)
    known_facts: dict[str, Any]  # field_name -> value or None
    
    # Context completeness
    context_score: int  # 0-100
    
    # Decision
    ready_to_proceed: bool
    
    # Next question (if not ready)
    next_question: str | None = None
    question_target: str | None = None  # Which field we're asking about
    simpler_alternative: str | None = None  # If user doesn't know
    
    # User intent detection
    user_said_unknown: bool = False  # User said "nežinau"
    user_wants_to_skip: bool = False  # User said "tiesiog padėkite"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _detect_user_intent(user_message: str) -> dict:
    """
    Detect if user wants to skip or says they don't know.
    
    Uses phrases from translation service (problem_types section).
    
    Returns:
        dict with 'wants_skip' and 'says_unknown' booleans
    """
    message_lower = user_message.lower()
    
    # Get phrases from translation (problem_types section in messages.yaml)
    skip_phrases = t_list("problem_types.skip_phrases")
    unknown_phrases = t_list("problem_types.unknown_phrases")
    
    # Fallback if translation not found
    if not skip_phrases:
        skip_phrases = ["skip", "just help", "nevermind", "tiesiog padėkite"]
    if not unknown_phrases:
        unknown_phrases = ["don't know", "nežinau", "not sure"]
    
    wants_skip = any(phrase in message_lower for phrase in skip_phrases)
    says_unknown = any(phrase in message_lower for phrase in unknown_phrases)
    
    return {
        "wants_skip": wants_skip,
        "says_unknown": says_unknown,
    }


def _merge_known_facts(existing: dict, new_facts: dict) -> dict:
    """
    Merge new facts into existing, preserving non-null values.
    
    Args:
        existing: Current known facts
        new_facts: Newly extracted facts
        
    Returns:
        Merged facts dict
    """
    merged = existing.copy()
    
    for key, value in new_facts.items():
        # Only update if new value is not None
        if value is not None:
            merged[key] = value
        # Keep existing value if new is None
        elif key not in merged:
            merged[key] = None
    
    return merged


def _build_analysis_prompt(
    user_message: str,
    problem_type: str,
    known_facts: dict,
    questions_asked: int,
    conversation_history: list[dict],
) -> str:
    """
    Build the full analysis prompt with all context.
    
    Args:
        user_message: Current user message
        problem_type: Current/detected problem type
        known_facts: Currently known facts
        questions_asked: Number of questions asked
        conversation_history: Previous messages
        
    Returns:
        Complete formatted prompt
    """
    # Get config values
    context_threshold = get_context_threshold(problem_type)
    max_questions = get_max_questions(problem_type)
    output_language = get_language_name()
    
    # Format prompt components
    problem_types_list = format_problem_types_list()
    context_fields_desc = format_context_fields_description(problem_type)
    known_facts_summary = format_known_facts_summary(known_facts)
    question_priority = format_question_priority(problem_type)
    history_text = build_conversation_history(conversation_history)
    
    # Get and format prompt template
    prompt = get_prompt(
        "problem_capture",
        "analyze_problem",
        user_message=user_message,
        current_problem_type=problem_type,
        problem_types_list=problem_types_list,
        context_fields_description=context_fields_desc,
        known_facts_summary=known_facts_summary,
        questions_asked=questions_asked,
        max_questions=max_questions,
        conversation_history=history_text,
        question_priority=question_priority,
        context_threshold=context_threshold,
        output_language=output_language,
    )
    
    # Add language instruction at the end
    language_instruction = f"""

CRITICAL LANGUAGE REQUIREMENT:
- The "next_question" field MUST be written in {output_language} language.
- The "problem_summary" field MUST be written in {output_language} language.
- The "simpler_alternative" field MUST be written in {output_language} language.
- All customer-facing text MUST be in {output_language}."""
    
    return prompt + language_instruction


def _get_acknowledgment(problem_type: str) -> str:
    """
    Get acknowledgment message for problem type.
    
    Args:
        problem_type: Detected problem type
        
    Returns:
        Translated acknowledgment message
    """
    # Try specific type first
    message = t(f"problem_capture.acknowledgment.{problem_type}")
    
    # Fallback to default
    if message.startswith("["):  # Translation not found
        message = t("problem_capture.acknowledgment.default")
    
    return message


def _get_translated_question(problem_type: str, field_key: str, use_simple: bool = False) -> str | None:
    """
    Get translated question from messages.yaml.
    
    Questions are stored in: problem_types.{type}.questions.{field}
    Simple versions: problem_types.{type}.questions.{field}_simple
    
    Args:
        problem_type: Problem type (internet, tv, etc.)
        field_key: Context field key (duration, scope, etc.)
        use_simple: Whether to use simpler version
        
    Returns:
        Translated question or None if not found
    """
    # Build translation key
    if use_simple:
        key = f"problem_types.{problem_type}.questions.{field_key}_simple"
    else:
        key = f"problem_types.{problem_type}.questions.{field_key}"
    
    question = t(key)
    
    # Check if translation found (t() returns [key] if not found)
    if question.startswith("["):
        # Try without _simple suffix as fallback
        if use_simple:
            key = f"problem_types.{problem_type}.questions.{field_key}"
            question = t(key)
            if question.startswith("["):
                return None
        else:
            return None
    
    return question


def _get_next_translated_question(
    problem_type: str, 
    known_facts: dict, 
    use_simple: bool = False
) -> tuple[str | None, str | None]:
    """
    Get next unanswered question from translation.
    
    Uses question_priority from config to determine order.
    
    Args:
        problem_type: Problem type
        known_facts: Already known facts
        use_simple: Use simpler questions
        
    Returns:
        Tuple of (question_text, field_key) or (None, None)
    """
    # Get question priority from config
    priority = get_question_priority(problem_type)
    
    if not priority:
        return None, None
    
    # Find first unanswered field
    for field_key in priority:
        if field_key not in known_facts or known_facts.get(field_key) is None:
            question = _get_translated_question(problem_type, field_key, use_simple)
            if question:
                return question, field_key
    
    return None, None


# =============================================================================
# MAIN NODE FUNCTION
# =============================================================================

def problem_capture_node(state: Any) -> dict:
    """
    Problem capture node - analyzes and qualifies customer problem.
    
    Flow:
    1. Get user message
    2. Detect problem type (from keywords or LLM)
    3. Extract known facts from conversation
    4. Calculate context score
    5. If score >= threshold OR questions >= max → proceed
    6. Otherwise → ask next qualifying question
    
    Args:
        state: Current conversation state
        
    Returns:
        State update dict
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    
    # Sync language from state (UI setting)
    lang = sync_language_from_state(state)
    
    logger.info(f"[{conversation_id}] Problem capture node started | language={lang}")
    
    # Get current state values
    user_message = get_last_user_message(state)
    current_problem_type = _get_attr(state, "problem_type")
    current_context = _get_attr(state, "problem_context", {})
    questions_asked = _get_attr(state, "qualifying_questions_asked", 0)
    qualifying_answers = _get_attr(state, "qualifying_answers", [])
    
    logger.debug(
        f"[{conversation_id}] State: type={current_problem_type}, "
        f"questions={questions_asked}, context_keys={list(current_context.keys())}"
    )
    
    # Handle missing message
    if not user_message:
        logger.warning(f"[{conversation_id}] No user message")
        return {
            "current_node": "problem_capture",
            "problem_type": current_problem_type or "other",
            "problem_description": user_message,
        }
    
    # === Step 1: Detect user intent ===
    intent = _detect_user_intent(user_message)
    
    if intent["wants_skip"]:
        logger.info(f"[{conversation_id}] User wants to skip qualifying questions")
    
    # === Step 2: Initial problem type detection (if not set) ===
    if not current_problem_type:
        detected_type = classify_problem_type_by_keywords(user_message)
        if detected_type:
            current_problem_type = detected_type
            logger.info(f"[{conversation_id}] Detected problem type from keywords: {detected_type}")
        else:
            current_problem_type = "other"  # Will be refined by LLM
    
    # === Step 3: Build prompt and call LLM ===
    conversation_history = _get_messages(state)
    
    prompt = _build_analysis_prompt(
        user_message=user_message,
        problem_type=current_problem_type,
        known_facts=current_context,
        questions_asked=questions_asked,
        conversation_history=conversation_history,
    )
    
    # Get system persona
    system_prompt = get_system_persona()
    
    # Add language instruction to system prompt
    output_language = get_language_name()
    system_prompt_with_lang = f"""{system_prompt}

LANGUAGE INSTRUCTION: You MUST generate all customer-facing text (next_question, problem_summary, simpler_alternative) in {output_language} language. This is critical."""
    
    messages = [
        {"role": "system", "content": system_prompt_with_lang},
        {"role": "user", "content": prompt}
    ]
    
    try:
        response = llm_json_completion(
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )
        
        analysis = ProblemAnalysis(**response)
        
        logger.info(
            f"[{conversation_id}] Analysis: type={analysis.problem_type}, "
            f"score={analysis.context_score}, ready={analysis.ready_to_proceed}"
        )
        
    except Exception as e:
        logger.error(f"[{conversation_id}] LLM error: {e}", exc_info=True)
        
        # Track error count
        current_error_count = _get_attr(state, "llm_error_count", 0) + 1
        
        if current_error_count >= 3:
            error_message = add_message(
                role="assistant",
                content=t("errors.llm_error"),
                node="problem_capture"
            )
            return {
                "messages": [error_message],
                "current_node": "problem_capture",
                "last_error": str(e),
                "llm_error_count": current_error_count,
                "conversation_ended": True,
            }
        
        # Fallback - ask generic question
        fallback_message = add_message(
            role="assistant",
            content=t("errors.not_understood"),
            node="problem_capture"
        )
        return {
            "messages": [fallback_message],
            "current_node": "problem_capture",
            "last_error": str(e),
            "llm_error_count": current_error_count,
        }
    
    # === Step 4: Update known facts ===
    updated_facts = _merge_known_facts(current_context, analysis.known_facts)
    updated_facts["context_score"] = analysis.context_score
    
    # Record Q&A if this was an answer to a question
    if questions_asked > 0:
        last_question = qualifying_answers[-1] if qualifying_answers else {}
        updated_answers = qualifying_answers + [{
            "question": last_question.get("next_question", ""),
            "answer": user_message,
            "target_field": last_question.get("target_field", ""),
            "understood": not analysis.user_said_unknown,
        }]
    else:
        updated_answers = qualifying_answers
    
    # === Step 5: Determine if ready to proceed ===
    threshold = get_context_threshold(analysis.problem_type)
    max_q = get_max_questions(analysis.problem_type)
    
    should_proceed = (
        analysis.ready_to_proceed or
        analysis.context_score >= threshold or
        questions_asked >= max_q or
        analysis.user_wants_to_skip or
        intent["wants_skip"]
    )
    
    logger.info(
        f"[{conversation_id}] Should proceed: {should_proceed} "
        f"(score={analysis.context_score}/{threshold}, q={questions_asked}/{max_q})"
    )
    
    if should_proceed:
        # === PROCEED TO NEXT NODE ===
        logger.info(f"[{conversation_id}] Context sufficient - proceeding to phone_lookup")
        
        # Build confirmation message
        acknowledgment = _get_acknowledgment(analysis.problem_type)
        
        if analysis.problem_summary:
            confirmation = f"{acknowledgment} {analysis.problem_summary}."
        else:
            confirmation = acknowledgment
        
        transition = t("problem_capture.transitioning")
        full_message = f"{confirmation} {transition}"
        
        message = add_message(
            role="assistant",
            content=full_message,
            node="problem_capture"
        )
        
        logger.info(f"[{conversation_id}] Problem capture complete | type={analysis.problem_type} | lang={get_language()}")
        
        return {
            "messages": [message],
            "current_node": "problem_capture",
            "problem_type": analysis.problem_type,
            "problem_description": analysis.problem_summary,
            "problem_context": updated_facts,
            "problem_capture_complete": True,
            "qualifying_questions_asked": questions_asked,
            "qualifying_answers": updated_answers,
        }
    
    else:
        # === ASK NEXT QUESTION ===
        logger.info(f"[{conversation_id}] Need more context - asking question #{questions_asked + 1}")
        
        # Determine which question to ask
        if analysis.user_said_unknown and analysis.simpler_alternative:
            # User didn't know - ask simpler version from LLM
            question_text = t("problem_capture.user_unknown") + " " + analysis.simpler_alternative
        else:
            # Use LLM's suggested question
            question_text = analysis.next_question
        
        # If no question from LLM, get translated question from messages.yaml
        if not question_text:
            question_text, target_field = _get_next_translated_question(
                analysis.problem_type, 
                updated_facts,
                use_simple=analysis.user_said_unknown
            )
            if target_field:
                analysis.question_target = target_field
        
        # Fallback question - generic
        if not question_text:
            question_text = t("problem_capture.ask_more_details")
        
        # First question - add acknowledgment
        if questions_asked == 0:
            acknowledgment = _get_acknowledgment(analysis.problem_type)
            full_message = f"{acknowledgment} {question_text}"
        else:
            full_message = question_text
        
        message = add_message(
            role="assistant",
            content=full_message,
            node="problem_capture"
        )
        
        # Track for next iteration
        new_answers = updated_answers + [{
            "next_question": question_text,
            "target_field": analysis.question_target,
        }]
        
        return {
            "messages": [message],
            "current_node": "problem_capture",
            "problem_type": analysis.problem_type,
            "problem_context": updated_facts,
            "qualifying_questions_asked": questions_asked + 1,
            "qualifying_answers": new_answers,
        }


# =============================================================================
# ROUTER FUNCTION
# =============================================================================

def problem_capture_router(state: Any) -> str:
    """
    Route after problem capture.
    
    Returns:
        - "end" → wait for user input (asked question or error)
        - "phone_lookup" → problem qualified, continue workflow
    """
    conversation_id = _get_attr(state, "conversation_id", "unknown")
    
    # Check if conversation ended (due to error)
    if _get_attr(state, "conversation_ended", False):
        logger.info(f"[{conversation_id}] Router → end (conversation ended)")
        return "end"
    
    # Check if problem capture is complete
    if _get_attr(state, "problem_capture_complete", False):
        problem_type = _get_attr(state, "problem_type")
        context_score = _get_attr(state, "problem_context", {}).get("context_score", 0)
        logger.info(f"[{conversation_id}] Router → phone_lookup (complete: {problem_type}, score: {context_score})")
        return "phone_lookup"
    
    # Check legacy fields for backward compatibility
    problem_type = _get_attr(state, "problem_type")
    problem_description = _get_attr(state, "problem_description")
    
    if problem_type and problem_description:
        logger.info(f"[{conversation_id}] Router → phone_lookup (legacy: {problem_type})")
        return "phone_lookup"
    
    # Asked a question - wait for user response
    logger.info(f"[{conversation_id}] Router → end (waiting for user)")
    return "end"
