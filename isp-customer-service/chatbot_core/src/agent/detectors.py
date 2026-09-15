"""Universal detector glosses — declarative perception meanings (Phase 3.11).

Loads knowledge/detectors.yaml: WHAT the caller's answers MEAN for each detector
TYPE (yes_no, restored, scope, instruct_done, ticket_consent, …), handed to the LLM
step-classifier as option definitions. Refining understanding is a FILE edit;
the code keeps only the arbitration mechanism.

Priority for a step's options (assembled by the engine):
    faults.yaml step `answers:`  (most specific, per step)
  → detectors.yaml               (this file — universal per detector type)

The schema checks the file covers every detector the code implements.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "detectors.yaml"

_cache: dict[str, dict[str, str]] | None = None


def _load() -> dict[str, dict[str, str]]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        import yaml

        raw = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        section = raw.get("detectors") or {}
        _cache = {
            str(name): {str(k): str(v) for k, v in (opts or {}).items()}
            for name, opts in section.items()
            if isinstance(opts, dict)
        }
    except Exception as e:  # fail-soft: knowledge must never break the call
        logger.warning(f"detectors.yaml not loaded ({e}); using code defaults")
        _cache = {}
    return _cache


def glosses(detector: str) -> dict[str, str]:
    """The universal answer meanings for a detector type ({} when undeclared)."""
    from .contract.locale import phrase

    return {key: phrase(text) for key, text in (_load().get(detector) or {}).items()}


def reload() -> None:
    """Drop the cache so the next read re-parses the file (tests / live tuning)."""
    global _cache
    _cache = None
