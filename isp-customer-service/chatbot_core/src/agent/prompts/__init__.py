"""
Prompt templates for the ISP Support Agent — composed from small Markdown pieces.

Structure (the speaker's prompt: the core plus ONE skill):
    speak/system.md      CORE, sent every turn (cached prefix)
    skills/*.md          one per SKILL a reply can need (wave 2b) - what to do NOW
    partials/*.md        reusable pieces (identity, facts integrity)
    sensors/*.md         the reading prompts (perception, classifier, solver...)

A prompt is assembled from partials with `<<include: partials/identity>>` markers, so a
shared rule (e.g. "one question") lives in ONE place. Files are plain Markdown (raw text
the model sees); only the small set of `{...}` placeholders in speak/system.md is
.format()-substituted.

Usage:
    from agent.prompts import load_node_prompt, load_speak_prompt
    sys = load_speak_prompt(caller_phone="+370...", language="lt")
    ask = load_node_prompt("skills/ask_fact")
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

# A line that is just `<<include: partials/identity>>` (optionally indented).
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
    """Load and compose a prompt (e.g. "speak/owners/intake") for the active locale.
    Raises PromptError on a missing file, include or examples entry."""
    return _localize(_expand(_read(name))).strip()


def check_prompts() -> None:
    """Compose every prompt file for the active locale — run at startup so a broken
    include or a missing examples entry fails the app, not a call."""
    for path in sorted(PROMPTS_DIR.rglob("*.md")):
        load_node_prompt(path.relative_to(PROMPTS_DIR).with_suffix("").as_posix())


def load_speak_prompt(caller_phone: str, language: str = "lt") -> str:
    """Load the speaker's CORE prompt (composes its partials, then fills placeholders)."""
    template = _localize(_expand(_read("speak/system")))
    return template.format(
        caller_phone=caller_phone,
        language_instruction=get_language_instruction(language),
        output_language=get_language_name(language),
    )
