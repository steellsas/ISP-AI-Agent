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
    """The output-language instruction (the model writes in this language) — the
    locale's `language_instruction` example."""
    from ..contract.locale import examples

    return examples("language_instruction")


def get_language_name(language: str) -> str:
    """The active locale's language name, for prompts."""
    from ..contract.locale import lang

    return lang().LANGUAGE_NAME


class PromptError(Exception):
    """A prompt cannot be composed (a missing file, include or examples entry)."""


def _read(relpath: str) -> str:
    """Read a prompt Markdown file by path relative to PROMPTS_DIR (no extension)."""
    try:
        with open(PROMPTS_DIR / f"{relpath}.md", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise PromptError(f"prompt '{relpath}': cannot read {relpath}.md ({e.strerror})") from e


def _expand(text: str, _seen: frozenset[str] = frozenset()) -> str:
    """Recursively replace `<<include: path>>` markers with the file's content.

    Cycle-safe: a path already being expanded resolves to empty (so a stray
    self/circular include can never loop forever).
    """

    def repl(match: re.Match) -> str:
        name = match.group(1)
        if name in _seen:
            return ""
        try:
            return _expand(_read(name), _seen | {name}).strip()
        except PromptError as e:
            raise PromptError(f"{e} — included from {sorted(_seen) or 'the top prompt'}") from e

    return _INCLUDE_RE.sub(repl, text)


def _localize(text: str) -> str:
    """Fill the language-specific parts: <<examples:…>> wording and <<language>>."""
    from ..contract.locale import LocaleError, expand_examples, lang

    try:
        return expand_examples(text).replace("<<language>>", lang().LANGUAGE_NAME)
    except LocaleError as e:
        raise PromptError(str(e)) from e


def load_node_prompt(name: str) -> str:
    """Load and compose a prompt (e.g. "stages/identification") for the active locale.
    Raises PromptError on a missing file, include or examples entry."""
    return _localize(_expand(_read(name))).strip()


def check_prompts() -> None:
    """Compose every prompt file for the active locale — run at startup so a broken
    include or a missing examples entry fails the app, not a call."""
    for path in sorted(PROMPTS_DIR.rglob("*.md")):
        load_node_prompt(path.relative_to(PROMPTS_DIR).with_suffix("").as_posix())


def load_system_prompt(
    tools_description: str,
    caller_phone: str,
    language: str = "lt",
) -> str:
    """Load the CORE system prompt (composes its partials, then fills placeholders)."""
    template = _localize(_expand(_read("system")))
    return template.format(
        tools_description=tools_description,
        caller_phone=caller_phone,
        language_instruction=get_language_instruction(language),
        output_language=get_language_name(language),
    )
