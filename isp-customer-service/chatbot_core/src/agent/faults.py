"""
Fault definitions loader — the declarative knowledge layer (Phase 3.8 step 5b/5c).

Reads `agent/knowledge/faults.yaml`, where each fault declares its playbook, how to
recognise that it is the caller's problem, and — per step — what each routing key MEANS
(i.e. what to detect in the caller's answer).

Why: the classifier needs the MEANING of a step's answers, and those meanings lived in
Python (`DETECTOR_GLOSSES` / `step.on`). Moving them here makes a new fault (or a reworded
check) a FILE edit, not a code change — the point of the whole migration. The code keeps
only the fallbacks and the safety enforcement.

Fail-soft by design: a missing/broken file simply yields no overrides and the engine falls
back to the in-code glosses, so a bad edit can never take the agent down.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_FAULTS_PATH = Path(__file__).resolve().parent / "knowledge" / "faults.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    """Parse the manifest once. Any failure -> empty (engine uses its code defaults)."""
    try:
        import yaml

        data = yaml.safe_load(_FAULTS_PATH.read_text(encoding="utf-8")) or {}
        faults = data.get("faults") or {}
        if not isinstance(faults, dict):
            return {}
        return faults
    except Exception as e:  # pragma: no cover - defensive; never break a call
        logger.warning(f"faults.yaml not loaded ({e}); using in-code defaults")
        return {}


def reload() -> None:
    """Drop the cache so an edited faults.yaml takes effect without a restart."""
    _load.cache_clear()


def step_options(verdict: str | None, step_id: str | None) -> dict[str, str] | None:
    """{routing key -> plain-language MEANING} for one step of one fault, or None when the
    manifest does not describe it (caller falls back to the per-detector glosses)."""
    if not verdict or not step_id:
        return None
    steps = (_load().get(verdict) or {}).get("steps") or {}
    opts = steps.get(step_id)
    if not isinstance(opts, dict) or not opts:
        return None
    return {str(k): str(v) for k, v in opts.items()}


def purpose_triggers() -> dict[str, list[str]]:
    """{fault id -> phrases that mean the caller has THIS problem}. Used to recognise the
    call's purpose from the manifest instead of a hard-coded keyword table."""
    out: dict[str, list[str]] = {}
    for fault, spec in _load().items():
        trig = (spec or {}).get("purpose_triggers") or []
        if isinstance(trig, list) and trig:
            out[fault] = [str(t) for t in trig]
    return out


def playbook(verdict: str | None) -> str | None:
    """The RAG doc holding this fault's step wording (as declared in the manifest)."""
    if not verdict:
        return None
    return (_load().get(verdict) or {}).get("playbook")
