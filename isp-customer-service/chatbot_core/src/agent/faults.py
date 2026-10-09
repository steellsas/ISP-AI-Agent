"""
Verdict flags — what the engine needs to know about a telemetry verdict
(`knowledge/verdicts.yaml`): is it a line fault, is the device visible, is the line
healthy up to the router, is it news to inform about, does it auto-register.

The v1 fault packs (`knowledge/faults/`) and their procedures used to live here too;
the v2 cards (`knowledge/v2/`, `contract/cards.py`) replaced them.

The file is read through contract.loader, which validates it at startup: a bad edit
stops the app with a readable error instead of misbehaving in a call.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

_KNOWLEDGE = Path(__file__).resolve().parent / "knowledge"
_VERDICTS_PATH = _KNOWLEDGE / "verdicts.yaml"
_FLAG_DEFAULTS: dict[str, Any] = {
    "unresolved_after_fix": False,
    "line_fault": False,
    "device_visible": True,
    "healthy_up_to_router": False,
    "inform": None,
    "auto_ticket": False,
}


@lru_cache(maxsize=1)
def _verdict_flags() -> dict[str, dict[str, Any]]:
    from .contract.loader import read_yaml

    return read_yaml(_VERDICTS_PATH) or {}


def verdict_flag(verdict: str | None, name: str) -> Any:
    """A verdict's flag from knowledge/verdicts.yaml (the default when unset)."""
    if name not in _FLAG_DEFAULTS:
        raise KeyError(f"unknown verdict flag '{name}'")
    return (_verdict_flags().get(verdict or "") or {}).get(name, _FLAG_DEFAULTS[name])


def reload() -> None:
    """Drop the derived cache (contract.loader.reload calls this)."""
    _verdict_flags.cache_clear()
