"""
Configuration Loader
Load YAML configs with caching for flexible, scalable configuration management.

Usage:
    from services.config_loader import get_problem_type_config, get_message

    # Get problem type config
    config = get_problem_type_config("internet")

    # Get formatted message
    msg = get_message("greeting", "welcome", agent_name="Andrius")
"""

import yaml
import random
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

# Setup paths
CONFIG_DIR = Path(__file__).parent.parent / "config"


# =============================================================================
# CORE LOADERS
# =============================================================================


@lru_cache(maxsize=10)
def load_config(config_name: str) -> dict:
    """
    Load YAML config file with caching.

    Args:
        config_name: Config file name without extension (e.g., "problem_types")

    Returns:
        Parsed YAML as dict

    Raises:
        FileNotFoundError: If config file doesn't exist
    """
    config_path = CONFIG_DIR / f"{config_name}.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def reload_configs():
    """Clear config cache - use after updating YAML files."""
    load_config.cache_clear()


# =============================================================================
# PROBLEM TYPES
# =============================================================================


def get_problem_types_config() -> dict:
    """Get full problem types configuration."""
    return load_config("problem_types")


def get_problem_type_config(problem_type: str) -> dict:
    """
    Get config for specific problem type.

    Args:
        problem_type: Type name (internet, tv, phone, billing, other)

    Returns:
        Problem type configuration dict
    """
    config = load_config("problem_types")
    return config["problem_types"].get(problem_type, config["problem_types"]["other"])


def get_all_problem_types() -> list[str]:
    """Get list of all problem type names."""
    config = load_config("problem_types")
    return list(config["problem_types"].keys())


def get_problem_type_keywords() -> dict[str, list[str]]:
    """
    Get keywords for all problem types.

    Returns:
        Dict mapping problem_type -> list of keywords
    """
    config = load_config("problem_types")
    return {
        ptype: pconfig.get("keywords", []) for ptype, pconfig in config["problem_types"].items()
    }


def get_context_fields(problem_type: str) -> dict:
    """
    Get context fields configuration for problem type.

    Args:
        problem_type: Type name

    Returns:
        Dict of field_name -> field_config
    """
    config = get_problem_type_config(problem_type)
    return config.get("context_fields", {})


def get_context_threshold(problem_type: str) -> int:
    """Get context threshold for problem type."""
    config = get_problem_type_config(problem_type)
    settings = load_config("problem_types").get("settings", {})
    return config.get("context_threshold", settings.get("default_context_threshold", 70))


def get_max_questions(problem_type: str) -> int:
    """Get max questions for problem type."""
    config = get_problem_type_config(problem_type)
    settings = load_config("problem_types").get("settings", {})
    return config.get("max_questions", settings.get("default_max_questions", 3))


def get_question_priority(problem_type: str) -> list[str]:
    """Get question priority order for problem type."""
    config = get_problem_type_config(problem_type)
    return config.get("question_priority", [])


def get_skip_phrases() -> list[str]:
    """Get phrases that indicate user wants to skip questions."""
    config = load_config("problem_types")
    return config.get("settings", {}).get("skip_phrases", [])


def get_unknown_phrases() -> list[str]:
    """Get phrases that indicate user doesn't know the answer."""
    config = load_config("problem_types")
    return config.get("settings", {}).get("unknown_phrases", [])


def _fuzzy_match(word: str, keyword: str, max_distance: int = 2) -> bool:
    """
    Simple fuzzy matching - checks if word is similar to keyword.
    Handles common typos like 'interentas' → 'internetas'.

    Args:
        word: Word to check
        keyword: Target keyword
        max_distance: Maximum edit distance allowed

    Returns:
        True if words are similar enough
    """
    if keyword in word or word in keyword:
        return True

    # Simple Levenshtein-like check for short words
    if abs(len(word) - len(keyword)) > max_distance:
        return False

    # Count matching characters
    matches = sum(1 for a, b in zip(word, keyword) if a == b)
    min_len = min(len(word), len(keyword))

    # If 70%+ characters match, consider it a match
    if min_len > 0 and matches / min_len >= 0.7:
        return True

    # Common Lithuanian typos/variations
    typo_mappings = {
        "interentas": "internetas",
        "interneto": "internetas",
        "interento": "internetas",
        "intrenetas": "internetas",
        "televizorius": "televizija",
        "televizijos": "televizija",
        "telefonas": "telefono",
        "saskaita": "sąskaita",
        "saskaitą": "sąskaita",
        "routeris": "router",
        "marsrutizatorius": "maršrutizatorius",
        "routerio": "router",
    }

    if word in typo_mappings:
        return typo_mappings[word] == keyword or keyword in typo_mappings[word]

    return False


def classify_problem_type_by_keywords(text: str) -> Optional[str]:
    """
    Classify problem type based on keywords in text.
    Uses fuzzy matching to handle typos.

    Args:
        text: User message text

    Returns:
        Problem type or None if no match
    """
    text_lower = text.lower()
    words = text_lower.replace(",", " ").replace(".", " ").split()
    keywords_map = get_problem_type_keywords()

    # Score each type
    scores = {}
    for ptype, keywords in keywords_map.items():
        if not keywords:  # Skip 'other' which has no keywords
            continue

        score = 0
        for kw in keywords:
            # Exact match
            if kw in text_lower:
                score += 2  # Higher weight for exact match
            else:
                # Fuzzy match for each word
                for word in words:
                    if _fuzzy_match(word, kw):
                        score += 1
                        break

        if score > 0:
            scores[ptype] = score

    if scores:
        # Return type with highest score
        return max(scores, key=scores.get)

    return None


def calculate_context_score(problem_type: str, known_facts: dict) -> int:
    """
    Calculate context completeness score based on known facts.

    Args:
        problem_type: Type name
        known_facts: Dict of field_name -> value (or None)

    Returns:
        Score 0-100
    """
    context_fields = get_context_fields(problem_type)

    if not context_fields:
        return 100  # No fields defined = always complete

    score = 0
    for field_name, field_config in context_fields.items():
        weight = field_config.get("weight", 0)
        value = known_facts.get(field_name)

        # Field has value (not None)
        if value is not None:
            score += weight

    return min(score, 100)


def get_next_question(
    problem_type: str, known_facts: dict, use_simpler: bool = False
) -> Optional[dict]:
    """
    Get next question to ask based on priority and what's already known.

    Args:
        problem_type: Type name
        known_facts: Dict of known field values
        use_simpler: If True, use simpler question variant

    Returns:
        Dict with question info or None if all known
    """
    priority = get_question_priority(problem_type)
    context_fields = get_context_fields(problem_type)

    for field_name in priority:
        # Skip if already known
        if known_facts.get(field_name) is not None:
            continue

        field_config = context_fields.get(field_name, {})
        question_key = "simpler_question" if use_simpler else "question"
        question = field_config.get(question_key) or field_config.get("question")

        if question:
            return {
                "field": field_name,
                "question": question,
                "simpler_question": field_config.get("simpler_question"),
                "description": field_config.get("description"),
            }

    return None


# =============================================================================
# MESSAGES
# =============================================================================


def get_messages_config() -> dict:
    """Get full messages configuration."""
    return load_config("messages")


def get_message(category: str, key: str, problem_type: str = None, **variables) -> str:
    """
    Get message template and fill variables.

    Args:
        category: Message category (e.g., "greeting", "closing")
        key: Message key within category
        problem_type: Optional problem type for type-specific messages
        **variables: Template variables to fill

    Returns:
        Formatted message string

    Examples:
        get_message("greeting", "welcome", agent_name="Andrius")
        get_message("problem_capture", "initial_acknowledgment", problem_type="internet")
        get_message("closing", "resolved", customer_suffix=", Jonas")
    """
    config = load_config("messages")

    category_config = config.get(category, {})
    template = category_config.get(key, "")

    # Handle nested dict (e.g., by problem_type)
    if isinstance(template, dict):
        if problem_type and problem_type in template:
            template = template[problem_type]
        else:
            template = template.get("default", "")

    # Handle list (pick random)
    if isinstance(template, list):
        template = random.choice(template) if template else ""

    # Format with variables
    if template and variables:
        try:
            return template.format(**variables)
        except KeyError:
            # Return template as-is if variable missing
            return template

    return template


def get_customer_suffix(customer_name: str = None) -> str:
    """
    Get customer suffix for messages.

    Args:
        customer_name: Full customer name or None

    Returns:
        Suffix like ", Jonas" or ""
    """
    if customer_name:
        first_name = customer_name.split()[0]
        return get_message("customer_suffix", "with_name", first_name=first_name)
    return get_message("customer_suffix", "without_name")


def get_confirmation_phrases(phrase_type: str = "yes") -> list[str]:
    """
    Get confirmation phrases list.

    Args:
        phrase_type: "yes" or "no"

    Returns:
        List of phrases
    """
    config = load_config("messages")
    key = f"{phrase_type}_phrases"
    return config.get("confirmations", {}).get(key, [])


def is_confirmation(text: str, phrase_type: str = "yes") -> bool:
    """
    Check if text is a confirmation phrase.

    Args:
        text: Text to check
        phrase_type: "yes" or "no"

    Returns:
        True if text matches confirmation phrase
    """
    phrases = get_confirmation_phrases(phrase_type)
    text_lower = text.lower().strip()
    return any(phrase in text_lower for phrase in phrases)


# =============================================================================
# CONTEXT FIELDS FORMATTING (for prompts)
# =============================================================================


def format_problem_types_list() -> str:
    """Format problem types list for prompt."""
    config = load_config("problem_types")
    lines = []
    for ptype, pconfig in config["problem_types"].items():
        display = pconfig.get("display_name", ptype)
        keywords = ", ".join(pconfig.get("keywords", [])[:5])
        lines.append(f"- {ptype}: {display} (keywords: {keywords}...)")
    return "\n".join(lines)


def format_context_fields_description(problem_type: str) -> str:
    """Format context fields description for prompt."""
    fields = get_context_fields(problem_type)
    lines = []
    for field_name, field_config in fields.items():
        weight = field_config.get("weight", 0)
        desc = field_config.get("description", "")
        lines.append(f"- {field_name} (weight: {weight}%): {desc}")
    return "\n".join(lines)


def format_known_facts_summary(known_facts: dict) -> str:
    """Format known facts for prompt."""
    if not known_facts or all(v is None for v in known_facts.values()):
        return "Kol kas nieko nežinoma."

    lines = []
    for field, value in known_facts.items():
        if value is not None:
            lines.append(f"- {field}: {value}")

    return "\n".join(lines) if lines else "Kol kas nieko nežinoma."


def format_question_priority(problem_type: str) -> str:
    """Format question priority for prompt."""
    priority = get_question_priority(problem_type)
    return " → ".join(priority) if priority else "Nėra prioriteto"
