"""
Prompt Loader
Load and format prompt templates from text files.

Usage:
    from services.prompt_loader import get_prompt, get_system_persona

    # Get formatted prompt
    prompt = get_prompt("problem_capture", "analyze_problem",
        user_message="neveikia internetas",
        problem_types_list="...",
    )

    # Get system persona
    persona = get_system_persona()
"""

from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

# Setup paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# =============================================================================
# CORE LOADERS
# =============================================================================


@lru_cache(maxsize=50)
def load_prompt_template(category: str, name: str) -> str:
    """
    Load prompt template from file.

    Args:
        category: Prompt category (folder name)
        name: Prompt name (file name without .txt)

    Returns:
        Prompt template string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    prompt_path = PROMPTS_DIR / category / f"{name}.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def reload_prompts():
    """Clear prompt cache - use after updating prompt files."""
    load_prompt_template.cache_clear()


# =============================================================================
# FORMATTED PROMPTS
# =============================================================================


def get_prompt(category: str, name: str, **variables) -> str:
    """
    Load prompt template and fill variables.

    Args:
        category: Prompt category (folder name)
        name: Prompt name
        **variables: Template variables

    Returns:
        Formatted prompt string

    Example:
        prompt = get_prompt("problem_capture", "analyze_problem",
            user_message="neveikia internetas",
            current_problem_type="internet",
            context_threshold=70,
        )
    """
    template = load_prompt_template(category, name)

    if variables:
        try:
            return template.format(**variables)
        except KeyError as e:
            # Log missing variable but don't fail
            print(f"Warning: Missing prompt variable: {e}")
            return template

    return template


def get_system_persona() -> str:
    """Get shared system persona prompt."""
    return load_prompt_template("shared", "system_persona")


# =============================================================================
# PROMPT HELPERS
# =============================================================================


def build_conversation_history(messages: list[dict], max_messages: int = 10) -> str:
    """
    Build conversation history string for prompts.

    Args:
        messages: List of message dicts with 'role' and 'content'
        max_messages: Maximum messages to include

    Returns:
        Formatted conversation history
    """
    if not messages:
        return "Pokalbis dar neprasidėjo."

    # Take last N messages
    recent = messages[-max_messages:] if len(messages) > max_messages else messages

    lines = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "user":
            lines.append(f"Klientas: {content}")
        elif role == "assistant":
            lines.append(f"Agentas: {content}")
        elif role == "system":
            lines.append(f"[Sistema: {content}]")

    return "\n".join(lines)


def build_known_facts_json(known_facts: dict) -> str:
    """
    Build JSON representation of known facts for prompts.

    Args:
        known_facts: Dict of field_name -> value

    Returns:
        JSON-like string
    """
    if not known_facts:
        return "{}"

    lines = ["{"]
    items = []
    for key, value in known_facts.items():
        if value is None:
            items.append(f'    "{key}": null')
        elif isinstance(value, bool):
            items.append(f'    "{key}": {str(value).lower()}')
        elif isinstance(value, str):
            items.append(f'    "{key}": "{value}"')
        else:
            items.append(f'    "{key}": {value}')

    lines.append(",\n".join(items))
    lines.append("}")

    return "\n".join(lines)


# =============================================================================
# PROBLEM CAPTURE PROMPTS
# =============================================================================


def get_problem_analysis_prompt(
    user_message: str,
    current_problem_type: str,
    known_facts: dict,
    questions_asked: int,
    conversation_history: list[dict],
    # Config values
    problem_types_list: str,
    context_fields_description: str,
    known_facts_summary: str,
    question_priority: str,
    context_threshold: int,
    max_questions: int,
) -> str:
    """
    Build complete problem analysis prompt with all variables.

    Args:
        user_message: Current user message
        current_problem_type: Detected/current problem type
        known_facts: Currently known facts
        questions_asked: Number of questions asked so far
        conversation_history: List of previous messages
        ... config values from config_loader

    Returns:
        Complete formatted prompt
    """
    return get_prompt(
        "problem_capture",
        "analyze_problem",
        user_message=user_message,
        current_problem_type=current_problem_type,
        known_facts_summary=known_facts_summary,
        questions_asked=questions_asked,
        max_questions=max_questions,
        conversation_history=build_conversation_history(conversation_history),
        problem_types_list=problem_types_list,
        context_fields_description=context_fields_description,
        question_priority=question_priority,
        context_threshold=context_threshold,
    )


# =============================================================================
# TROUBLESHOOTING PROMPTS
# =============================================================================


def get_troubleshooting_prompt(category: str, name: str, **variables) -> str:
    """
    Get troubleshooting-related prompt.

    Args:
        category: Should be "troubleshooting"
        name: Prompt name
        **variables: Template variables

    Returns:
        Formatted prompt
    """
    return get_prompt(category, name, **variables)


# =============================================================================
# LIST AVAILABLE PROMPTS
# =============================================================================


def list_available_prompts() -> dict[str, list[str]]:
    """
    List all available prompts by category.

    Returns:
        Dict mapping category -> list of prompt names
    """
    prompts = {}

    if not PROMPTS_DIR.exists():
        return prompts

    for category_dir in PROMPTS_DIR.iterdir():
        if category_dir.is_dir() and not category_dir.name.startswith("."):
            category = category_dir.name
            prompt_files = [f.stem for f in category_dir.glob("*.txt")]
            if prompt_files:
                prompts[category] = prompt_files

    return prompts
