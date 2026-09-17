"""Universal detector glosses — declarative perception meanings (Phase 3.11).

Loads knowledge/detectors.yaml: WHAT the caller's answers MEAN for each detector
TYPE (yes_no, restored, scope, instruct_done, ticket_consent, …), handed to the LLM
step-classifier as option definitions. Refining understanding is a FILE edit;
the code keeps only the arbitration mechanism.

Priority for a step's options (assembled by the engine):
    a fault pack step `answers:`  (most specific, per step)
  → detectors.yaml               (this file — universal per detector type)

The schema checks the file covers every detector the code implements.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "detectors.yaml"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, str]]:
    from .contract.loader import read_yaml

    section = (read_yaml(_PATH) or {}).get("detectors") or {}
    return {
        str(name): {str(k): str(v) for k, v in (opts or {}).items()}
        for name, opts in section.items()
        if isinstance(opts, dict)
    }


def glosses(detector: str) -> dict[str, str]:
    """The universal answer meanings for a detector type ({} when undeclared)."""
    from .contract.locale import phrase

    return {key: phrase(text) for key, text in (_load().get(detector) or {}).items()}


def reload() -> None:
    """Drop the derived cache (contract.loader.reload calls this)."""
    _load.cache_clear()
