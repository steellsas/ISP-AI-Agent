"""Serve a troubleshooting playbook ONE step at a time.

A streaming LLM handed a whole troubleshooting markdown dumps 3-4 steps as a
monologue, breaking the "one step per reply, then wait" rule. So instruct steps
live under `### Žingsnis N: …` headers, and the engine injects only the CURRENT
step's section into the prompt — never the whole file.

Pure text parsing here (no I/O beyond reading the doc file by path); the engine
tracks which step we are on and calls get_step().
"""

from __future__ import annotations

import re
from pathlib import Path

# Knowledge base lives next to this package: agent/ -> ../rag/knowledge_base/.
_KB_DIR = Path(__file__).resolve().parent.parent / "rag" / "knowledge_base"

# A step heading: "### Žingsnis 1: Lemputės" (the number makes it a step, so a
# plain "### Kada eskaluoti" section is not mistaken for one).
_STEP_RE = re.compile(r"^###\s+Žingsnis\s+\d+.*$", re.MULTILINE)


def parse_steps(text: str) -> list[str]:
    """Return each `### Žingsnis N …` section (heading + its body), in order.

    Non-step content (title, Simptomai, Kada eskaluoti…) is ignored — only the
    numbered steps are served to the caller one at a time.
    """
    if not text:
        return []
    marks = list(_STEP_RE.finditer(text))
    steps: list[str] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        steps.append(text[m.start() : end].strip())
    return steps


def _load_doc(rag_doc: str) -> str | None:
    """Read a KB doc by its path (e.g. 'troubleshooting/internet_..._mac'),
    with or without the .md suffix. None if it does not exist."""
    if not rag_doc:
        return None
    rel = rag_doc if rag_doc.endswith(".md") else f"{rag_doc}.md"
    path = _KB_DIR / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def full_doc(rag_doc: str) -> str | None:
    """The ENTIRE playbook text. The walker injects ONE step at a time (so a narrating
    model cannot run ahead), but the SOLVER reasons over the whole procedure to pick the
    next action — it needs the full doc, not a single section."""
    return _load_doc(rag_doc)


def get_step(rag_doc: str, index: int) -> str | None:
    """The `index`-th (0-based) `### Žingsnis` section of a KB playbook, or None
    if the doc is missing or the index is out of range."""
    text = _load_doc(rag_doc)
    if text is None:
        return None
    steps = parse_steps(text)
    return steps[index] if 0 <= index < len(steps) else None


def step_count(rag_doc: str) -> int:
    """How many `### Žingsnis` steps a playbook has (0 if missing)."""
    text = _load_doc(rag_doc)
    return len(parse_steps(text)) if text else 0
