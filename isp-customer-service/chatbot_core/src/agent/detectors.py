"""Universal detector glosses — declarative perception meanings (Phase 3.11).

Loads knowledge/detectors.yaml: WHAT the caller's answers MEAN for each detector
TYPE (yes_no, restored, scope, instruct_done, ticket_consent, …), handed to the LLM
step-classifier as option definitions. Refining understanding is a FILE edit;
the code keeps only the arbitration mechanism.

Priority for a step's options (assembled by the engine):
    faults.yaml step `answers:`  (most specific, per step)
  → detectors.yaml               (this file — universal per detector type)
  → code defaults                (resolution.DETECTOR_GLOSSES + _EXTRA_DEFAULTS)

Fail-soft like the other knowledge loaders: a missing or broken file silently
falls back to the code defaults and the call continues.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "detectors.yaml"

_cache: dict[str, dict[str, str]] | None = None

# Code defaults for detectors that historically lived OUTSIDE resolution.py's
# DETECTOR_GLOSSES (they were hardcoded at their call sites). Kept here so the
# engine still understands these answers with no YAML present.
_EXTRA_DEFAULTS: dict[str, dict[str, str]] = {
    "instruct_done": {
        "done": (
            "klientas atliko / jau padarė tai, ko buvo prašyta, ARBA praneša "
            "REZULTATĄ po veiksmo ('įkišau', 'ryšys yra, bet interneto nėra', "
            "'vis tiek neveikia') — rezultato pranešimas reiškia, kad veiksmas atliktas"
        ),
        "waiting": (
            "klientas dar daro, ruošiasi, ką tik pradėjo, klausia KAIP atlikti, "
            "arba nesupranta instrukcijos"
        ),
    },
    "ticket_consent": {
        "yes": "sutinka, kad užregistruotume gedimą (pritaria, sako gerai/tinka)",
        "no": "AIŠKIAI atsisako registracijos — NE šiaip nerišlus atsakymas",
    },
}


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
    """The universal answer meanings for a detector type. File wins; code defaults
    (resolution.DETECTOR_GLOSSES + _EXTRA_DEFAULTS) are the fallback."""
    from_file = _load().get(detector)
    if from_file:
        return from_file
    from .resolution import DETECTOR_GLOSSES

    return DETECTOR_GLOSSES.get(detector) or _EXTRA_DEFAULTS.get(detector, {})


def reload() -> None:
    """Drop the cache so the next read re-parses the file (tests / live tuning)."""
    global _cache
    _cache = None
