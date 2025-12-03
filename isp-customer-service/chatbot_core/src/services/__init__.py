# """
# Services module - LLM, config, prompts and external integrations
# """

# from .llm import llm_completion, llm_json_completion
# from .config_loader import (
#     load_config,
#     reload_configs,
#     get_problem_type_config,
#     get_problem_types_config,
#     get_all_problem_types,
#     get_context_fields,
#     get_context_threshold,
#     get_max_questions,
#     get_question_priority,
#     get_skip_phrases,
#     get_unknown_phrases,
#     classify_problem_type_by_keywords,
#     calculate_context_score,
#     get_next_question,
#     get_message,
#     get_customer_suffix,
#     is_confirmation,
#     format_problem_types_list,
#     format_context_fields_description,
#     format_known_facts_summary,
#     format_question_priority,
# )
# from .prompt_loader import (
#     load_prompt_template,
#     reload_prompts,
#     get_prompt,
#     get_system_persona,
#     build_conversation_history,
#     get_problem_analysis_prompt,
# )

# __all__ = [
#     # LLM
#     "llm_completion",
#     "llm_json_completion",
#     # Config
#     "load_config",
#     "reload_configs",
#     "get_problem_type_config",
#     "get_problem_types_config",
#     "get_all_problem_types",
#     "get_context_fields",
#     "get_context_threshold",
#     "get_max_questions",
#     "get_question_priority",
#     "get_skip_phrases",
#     "get_unknown_phrases",
#     "classify_problem_type_by_keywords",
#     "calculate_context_score",
#     "get_next_question",
#     "get_message",
#     "get_customer_suffix",
#     "is_confirmation",
#     "format_problem_types_list",
#     "format_context_fields_description",
#     "format_known_facts_summary",
#     "format_question_priority",
#     # Prompts
#     "load_prompt_template",
#     "reload_prompts",
#     "get_prompt",
#     "get_system_persona",
#     "build_conversation_history",
#     "get_problem_analysis_prompt",
# ]

"""
Services Package

Shared services for the ISP customer service chatbot.

Services:
- language_service: Language management (LT/EN) with state sync
- translation_service: Translation loading and t() function
- llm: LLM completion calls
- crm: CRM service wrapper
- network: Network diagnostics wrapper
"""

# Language and Translation
from .language_service import (
    # Basic functions
    set_language,
    get_language,
    get_language_name,
    get_agent_name,
    get_language_config,
    get_available_languages,
    is_valid_language,
    # State synchronization
    sync_language_from_state,
    language_from_state,
    clear_conversation_language,
    # LLM helpers
    get_output_language_instruction,
    get_language_context,
    # Constants
    DEFAULT_LANGUAGE,
    FALLBACK_LANGUAGE,
    LANGUAGE_CONFIG,
    # Type definitions (backward compatibility)
    SupportedLanguage,
)

from .translation_service import (
    t,
    t_list,
    t_dict,
    has_translation,
    reload_translations,
)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Language Service - Basic
    "set_language",
    "get_language",
    "get_language_name",
    "get_agent_name",
    "get_language_config",
    "get_available_languages",
    "is_valid_language",
    
    # Language Service - State Sync
    "sync_language_from_state",
    "language_from_state",
    "clear_conversation_language",
    
    # Language Service - LLM Helpers
    "get_output_language_instruction",
    "get_language_context",
    
    # Language Service - Constants
    "DEFAULT_LANGUAGE",
    "FALLBACK_LANGUAGE",
    "LANGUAGE_CONFIG",
    
    # Language Service - Types (backward compatibility)
    "SupportedLanguage",
    
    # Translation Service
    "t",
    "t_list",
    "t_dict",
    "has_translation",
    "reload_translations",
]