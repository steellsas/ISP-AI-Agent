"""
Services module - LLM, config, prompts and external integrations
"""

from .llm import llm_completion, llm_json_completion
from .config_loader import (
    load_config,
    reload_configs,
    get_problem_type_config,
    get_problem_types_config,
    get_all_problem_types,
    get_context_fields,
    get_context_threshold,
    get_max_questions,
    get_question_priority,
    get_skip_phrases,
    get_unknown_phrases,
    classify_problem_type_by_keywords,
    calculate_context_score,
    get_next_question,
    get_message,
    get_customer_suffix,
    is_confirmation,
    format_problem_types_list,
    format_context_fields_description,
    format_known_facts_summary,
    format_question_priority,
)
from .prompt_loader import (
    load_prompt_template,
    reload_prompts,
    get_prompt,
    get_system_persona,
    build_conversation_history,
    get_problem_analysis_prompt,
)

__all__ = [
    # LLM
    "llm_completion",
    "llm_json_completion",
    # Config
    "load_config",
    "reload_configs",
    "get_problem_type_config",
    "get_problem_types_config",
    "get_all_problem_types",
    "get_context_fields",
    "get_context_threshold",
    "get_max_questions",
    "get_question_priority",
    "get_skip_phrases",
    "get_unknown_phrases",
    "classify_problem_type_by_keywords",
    "calculate_context_score",
    "get_next_question",
    "get_message",
    "get_customer_suffix",
    "is_confirmation",
    "format_problem_types_list",
    "format_context_fields_description",
    "format_known_facts_summary",
    "format_question_priority",
    # Prompts
    "load_prompt_template",
    "reload_prompts",
    "get_prompt",
    "get_system_persona",
    "build_conversation_history",
    "get_problem_analysis_prompt",
]