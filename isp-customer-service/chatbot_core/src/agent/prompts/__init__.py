"""
Prompt templates for the ISP Support Agent — composed from small Markdown pieces.

Structure (dynamic per-stage prompting):
    system.md            CORE, sent every turn (cached prefix)
    partials/*.md        reusable pieces (identity, style, region, phases...)
    stages/*.md          one per LangGraph node — pure composition via <<include>>

A stage prompt is assembled from partials with `<<include: partials/style>>`
markers, so a shared rule (e.g. "one question") lives in ONE place and every stage
that includes it stays in sync. Files are plain Markdown (raw text the model sees);
only the small set of `{...}` placeholders in system.md is .format()-substituted.

Usage:
    from agent.prompts import load_system_prompt, load_node_prompt
    sys = load_system_prompt(tools_description="...", caller_phone="+370...", language="lt")
    addr = load_node_prompt("stages/identification")
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

# A line that is just `<<include: partials/style>>` (optionally indented).
_INCLUDE_RE = re.compile(r"^[ \t]*<<include:\s*([\w./_-]+)\s*>>[ \t]*$", re.MULTILINE)


def get_language_instruction(language: str) -> str:
    """Get the output-language instruction (the model writes in this language)."""
    if language == "lt":
        return """You MUST respond in POLITE formal Lithuanian ("Jūs" form). This is mandatory!
- ✅ CORRECT: "Ar galėtumėte patikrinti?", "Palaukite, patikrinsiu", "Perkraukite routerį"
- ❌ WRONG: informal "tu" forms ("ar gali", "palauk", "perkrauk")
- Polite and warm, but professional - no "gerbiamas kliente" stiffness"""
    return """You MUST respond in English. Be friendly and casual.
- Use simple, clear language
- Be helpful and professional"""


def get_language_name(language: str) -> str:
    """Get language name for prompts."""
    return "Lithuanian" if language == "lt" else "English"


def _read(relpath: str) -> str:
    """Read a prompt Markdown file by path relative to PROMPTS_DIR (no extension)."""
    with open(PROMPTS_DIR / f"{relpath}.md", encoding="utf-8") as f:
        return f.read()


def _expand(text: str, _seen: frozenset[str] = frozenset()) -> str:
    """Recursively replace `<<include: path>>` markers with the file's content.

    Cycle-safe: a path already being expanded resolves to empty (so a stray
    self/circular include can never loop forever).
    """

    def repl(match: re.Match) -> str:
        name = match.group(1)
        if name in _seen:
            return ""
        return _expand(_read(name), _seen | {name}).strip()

    return _INCLUDE_RE.sub(repl, text)


def load_node_prompt(name: str) -> str:
    """Load and compose a stage prompt (e.g. "stages/identification")."""
    return _expand(_read(name)).strip()


def load_system_prompt(
    tools_description: str,
    caller_phone: str,
    language: str = "lt",
) -> str:
    """Load the CORE system prompt (composes its partials, then fills placeholders)."""
    template = _expand(_read("system"))
    return template.format(
        tools_description=tools_description,
        caller_phone=caller_phone,
        language_instruction=get_language_instruction(language),
        output_language=get_language_name(language),
    )


def get_prompt_path(name: str) -> Path:
    """Get path to a prompt file (kept for the .txt greeting helper)."""
    return PROMPTS_DIR / f"{name}.txt"
