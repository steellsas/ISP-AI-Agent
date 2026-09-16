"""Call intents — what the caller wants, and what the agent does about it (D-11).

`knowledge/intents.yaml` declares each intent: how it is recognised (trigger words, then
an LLM pick from the descriptions), and its POLICY — solve the fault, register a ticket of
a type, answer from data, say it is not ours, or just talk. Code enforces the behaviour
per policy; the file decides which intent gets which."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_INTENTS_PATH = Path(__file__).parent / "knowledge" / "intents.yaml"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    """The intents catalog (knowledge/intents.yaml `intents:`)."""
    from .contract.loader import read_yaml

    data = read_yaml(_INTENTS_PATH) or {}
    intents = data.get("intents") if isinstance(data, dict) else None
    return intents if isinstance(intents, dict) else {}


def reload() -> None:
    _catalog.cache_clear()


def classify_purpose(text: str | None) -> str | None:
    """The caller's intent from the utterance, using the catalog's triggers.
    Order matters (a specific problem before a broader one), which YAML preserves.
    Returns None when nothing matches, so the caller can fall back to its own table."""
    if not text:
        return None
    from .contract.locale import vocab

    low = f" {text.lower()} "
    problems = _catalog()
    if not isinstance(problems, dict):
        return None
    for problem, spec in problems.items():
        name = (spec or {}).get("triggers_vocab")
        for trig in vocab(name) if name else ():
            if str(trig).lower() in low:
                return str(problem)
    return None


def intent_service(problem: str | None) -> str | None:
    """The service a complaint is about (knowledge/intents.yaml `service`), or None."""
    return problem_entry(problem).get("service") or None


def problem_entry(problem: str | None) -> dict[str, Any]:
    """The classification-catalog entry for a PROBLEM type (problems: section)."""
    if not problem:
        return {}
    entry = (_catalog() or {}).get(problem)
    return entry if isinstance(entry, dict) else {}


BOUNDARY_POLICIES = frozenset({"not_ours", "chat"})


def problem_policy(problem: str | None) -> str:
    """The competence policy for a problem type: solve (default) | register | answer |
    not_ours | chat. Files declare WHAT the agent solves; code only enforces the
    behaviour per policy."""
    v = problem_entry(problem).get("policy")
    return str(v) if v in ("solve", "register", "answer", "not_ours", "chat") else "solve"


def problem_boundary_reply(problem: str | None) -> str | None:
    """The scripted boundary reply for a not_ours / chat type."""
    from .contract.locale import maybe_phrase

    return maybe_phrase(problem_entry(problem).get("boundary_reply_key"))


def problem_confirm_question(problem: str | None) -> str | None:
    """The explicit-confirmation question for a medium-confidence LLM guess."""
    from .contract.locale import maybe_phrase

    return maybe_phrase(problem_entry(problem).get("confirm_question_key"))


def problem_catalog_options() -> dict[str, str]:
    """{type: meaning} for the L2 LLM classifier — each entry's `description`
    plus a couple of the locale's example phrasings. Only entries WITH a
    description participate (a triggers-only entry stays L1-only)."""
    from .contract.locale import examples

    out: dict[str, str] = {}
    for name, entry in (_catalog() or {}).items():
        if not isinstance(entry, dict):
            continue
        desc = entry.get("description")
        if not desc:
            continue
        key = entry.get("examples_key")
        samples = [ln for ln in examples(key).splitlines() if ln.strip()][:2] if key else []
        out[str(name)] = str(desc) + (f" (e.g.: {'; '.join(samples)})" if samples else "")
    return out
