"""
Identification policy loader — the declarative direction knobs (Phase 3.8 step 5d).

The identification PROCEDURE wording is the prompt partial `prompts/partials/identification.md`;
this reads `agent/knowledge/identification.yaml` for the DIRECTION knobs a dev flips
(offer the phone address first, require an apartment, ask an extra verification question).
The engine reflects these in the identification guidance so changing them — including adding
an extra question like the caller's name — is a file edit, not a code change.

The GUARDS are NOT here (tool gate, apartment-never-from-DB, street-must-match); security
boundaries stay in code. Fail-soft: a missing/broken file yields the built-in defaults, so
a bad edit cannot take identification down.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "identification.yaml"

# Built-in defaults = today's behaviour, used when the file is absent/malformed.
_DEFAULTS: dict[str, Any] = {
    "offer_phone_address": True,
    "require_apartment": True,
    "extra_questions": [],
    "questions": {},
}


@lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        cfg = (data.get("identification") or {}) if isinstance(data, dict) else {}
        return {**_DEFAULTS, **cfg} if isinstance(cfg, dict) else dict(_DEFAULTS)
    except Exception as e:  # pragma: no cover - defensive; never break a call
        logger.warning(f"identification.yaml not loaded ({e}); using defaults")
        return dict(_DEFAULTS)


def reload() -> None:
    _cfg.cache_clear()


def offer_phone_address() -> bool:
    return bool(_cfg().get("offer_phone_address", True))


def require_apartment() -> bool:
    return bool(_cfg().get("require_apartment", True))


def extra_questions_guidance() -> str | None:
    """A guidance line for any configured extra verification questions, injected into the
    identification facts so the agent asks + confirms them before proceeding. None when
    none are configured (today's default = address only)."""
    cfg = _cfg()
    wanted = cfg.get("extra_questions") or []
    phrasings = cfg.get("questions") or {}
    asks = [str(phrasings.get(q, q)) for q in wanted if q]
    if not asks:
        return None
    joined = " ".join(f'"{a}"' for a in asks)
    return (
        "- EXTRA VERIFICATION: besides the address, also ask and confirm: "
        + joined
        + " Ask ONE thing at a time and wait; do these before treating the caller as fully "
        "identified."
    )
