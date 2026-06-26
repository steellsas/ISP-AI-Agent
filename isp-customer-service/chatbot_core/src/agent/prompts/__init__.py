"""
Prompt templates for ISP Support Agent.

Usage:
    from agent.prompts import load_system_prompt

    prompt = load_system_prompt(
        tools_description="...",
        caller_phone="+37060012345",
        language="lt"
    )
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def get_language_instruction(language: str) -> str:
    """
    Get language instruction for system prompt.

    Args:
        language: Language code ("lt" or "en")

    Returns:
        Instruction string for LLM
    """
    if language == "lt":
        return """You MUST respond in POLITE formal Lithuanian ("Jūs" form). This is mandatory!
- ✅ CORRECT: "Ar galėtumėte patikrinti?", "Palaukite, patikrinsiu", "Perkraukite routerį"
- ❌ WRONG: informal "tu" forms ("ar gali", "palauk", "perkrauk")
- Polite and warm, but professional - no "gerbiamas kliente" stiffness"""
    else:
        return """You MUST respond in English. Be friendly and casual.
- Use simple, clear language
- Be helpful and professional"""


def get_language_name(language: str) -> str:
    """Get language name for prompts."""
    return "Lithuanian" if language == "lt" else "English"


def load_system_prompt(
    tools_description: str,
    caller_phone: str,
    language: str = "lt",
) -> str:
    """
    Load and format the system prompt.

    Args:
        tools_description: Description of available tools
        caller_phone: Caller's phone number
        language: Language code ("lt" or "en")

    Returns:
        Formatted system prompt string
    """
    prompt_path = PROMPTS_DIR / "system_prompt.txt"

    with open(prompt_path, encoding="utf-8") as f:
        template = f.read()

    return template.format(
        tools_description=tools_description,
        caller_phone=caller_phone,
        language_instruction=get_language_instruction(language),
        output_language=get_language_name(language),
    )


def load_node_prompt(name: str) -> str:
    """Load a per-stage node prompt (address_node / diagnosis_node / closing_node).

    Dynamic per-stage prompting (LangGraph): each stage gets ONLY its own rules so
    the model is not diluted by the whole call's instructions. The shared
    conversation contract + facts live in the system prompt and the KNOWN FACTS
    block; these files carry just the stage focus.
    """
    with open(PROMPTS_DIR / f"{name}.txt", encoding="utf-8") as f:
        return f.read().strip()


def get_prompt_path(name: str) -> Path:
    """Get path to a prompt file."""
    return PROMPTS_DIR / f"{name}.txt"
