"""
Fault knowledge loader — the declarative layer (Phase 3.8 step 5b/5c).

Reads `agent/knowledge/faults.yaml`, which holds:
  * `problems` — the call's PURPOSE and the phrases that signal it (what the CALLER
    reports), and
  * `faults`   — each CAUSE the telemetry can reach: its playbook, and the full
    procedure (steps: kind, detector, routing, rag section, hint, and what each
    routing key MEANS).

Why: the procedure and the answer meanings used to live in Python (`STRATEGIES`,
`DETECTOR_GLOSSES`, `_PROBLEM_KEYWORDS`). Moving them here makes a new fault — or a
reworded check — a FILE edit rather than a code change, which is the whole point of the
migration. Code keeps the mechanism and the safety enforcement.

Fail-soft by design: anything missing or malformed yields None/{} and the engine falls
back to its in-code defaults, so a bad edit can never take the agent down.
"""

from __future__ import annotations

import logging
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FAULTS_PATH = Path(__file__).resolve().parent / "knowledge" / "faults.yaml"


@lru_cache(maxsize=1)
def _doc() -> dict[str, Any]:
    """Parse the manifest once. Any failure -> empty (engine uses its code defaults)."""
    try:
        import yaml

        data = yaml.safe_load(_FAULTS_PATH.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:  # pragma: no cover - defensive; never break a call
        logger.warning(f"faults.yaml not loaded ({e}); using in-code defaults")
        return {}


def _faults() -> dict[str, Any]:
    f = _doc().get("faults")
    return f if isinstance(f, dict) else {}


def reload() -> None:
    """Drop the caches so an edited faults.yaml takes effect without a restart."""
    _doc.cache_clear()
    build_strategy.cache_clear()


# --- Purpose: what the CALLER reports -------------------------------------------


def classify_purpose(text: str | None) -> str | None:
    """The reported problem type from the utterance, using the manifest's triggers.
    Order matters (a specific problem before a broader one), which YAML preserves.
    Returns None when nothing matches, so the caller can fall back to its own table."""
    if not text:
        return None
    low = f" {text.lower()} "
    problems = _doc().get("problems")
    if not isinstance(problems, dict):
        return None
    for problem, spec in problems.items():
        for trig in (spec or {}).get("triggers") or []:
            if str(trig).lower() in low:
                return str(problem)
    return None


# --- Detection: what each routing key MEANS -------------------------------------


def step_options(verdict: str | None, step_id: str | None) -> dict[str, str] | None:
    """{routing key -> plain-language MEANING} for one step, or None when undeclared
    (caller falls back to the generic per-detector glosses in code)."""
    if not verdict or not step_id:
        return None
    for step in (_faults().get(verdict) or {}).get("steps") or []:
        if isinstance(step, dict) and step.get("id") == step_id:
            answers = step.get("answers")
            if isinstance(answers, dict) and answers:
                return {str(k): str(v) for k, v in answers.items()}
            return None
    return None


def playbook(verdict: str | None) -> str | None:
    """The RAG doc holding this fault's step wording."""
    if not verdict:
        return None
    return (_faults().get(verdict) or {}).get("playbook")


# --- Procedure: the steps themselves --------------------------------------------


@cache
def build_strategy(verdict: str):
    """Build a Strategy from the manifest, or None if this fault is not declared there
    (the caller then uses the in-code registry). Built objects are the SAME dataclasses
    the walker already consumes, so nothing downstream changes."""
    spec = _faults().get(verdict)
    if not isinstance(spec, dict) or not spec.get("steps"):
        return None
    try:
        from .resolution import Step, StepKind, Strategy

        steps = []
        for raw in spec["steps"]:
            steps.append(
                Step(
                    id=str(raw["id"]),
                    kind=StepKind(str(raw["kind"])),
                    hint=str(raw.get("hint", "")),
                    tools=frozenset(raw.get("tools") or ()),
                    tool_actions=tuple(raw.get("tool_actions") or ()),
                    rag_section=raw.get("rag_section"),
                    detector=str(raw.get("detector", "")),
                    on={str(k): str(v) for k, v in (raw.get("on") or {}).items()},
                    goto=str(raw.get("goto", "")),
                )
            )
        return Strategy(
            verdict=verdict,
            rag_doc=str(spec.get("playbook", "")),
            steps=tuple(steps),
        )
    except Exception as e:  # a malformed entry must not break the call
        logger.warning(f"faults.yaml: cannot build strategy for {verdict} ({e})")
        return None
