"""
Identification policy loader — the declarative direction knobs (Phase 3.8 step 5d).

The identification PROCEDURE wording is the prompt partial `prompts/partials/identification.md`;
this reads `agent/knowledge/identification.yaml` for the DIRECTION knobs a dev flips
(offer the phone address first, require an apartment, ask an extra verification question).
The engine reflects these in the identification guidance so changing them — including adding
an extra question like the caller's name — is a file edit, not a code change.

The GUARDS are NOT here (tool gate, apartment-never-from-DB, street-must-match); security
boundaries stay in code. An unset knob takes its default.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "identification.yaml"

# The knob defaults, used for any knob the file does not set.
_DEFAULTS: dict[str, Any] = {
    "offer_phone_address": True,
    "require_apartment": True,
    "ask_caller": True,
    "extra_questions": [],
}


@lru_cache(maxsize=1)
def _cfg() -> dict[str, Any]:
    from .contract.loader import read_yaml

    data = read_yaml(_PATH) or {}
    cfg = (data.get("identification") or {}) if isinstance(data, dict) else {}
    return {**_DEFAULTS, **cfg} if isinstance(cfg, dict) else dict(_DEFAULTS)


def reload() -> None:
    _cfg.cache_clear()


def offer_phone_address() -> bool:
    return bool(_cfg().get("offer_phone_address", True))


def require_apartment() -> bool:
    return bool(_cfg().get("require_apartment", True))


def ask_caller() -> bool:
    """Ask WHO is calling (name + relation to the contract) once the address is
    confirmed — for the call record and identification confidence, never a gate."""
    return bool(_cfg().get("ask_caller", True))


def caller_question() -> str:
    from .contract.locale import phrase

    return phrase("identification.questions.caller")


def extra_questions_guidance() -> str | None:
    """A guidance line for any configured extra verification questions, injected into the
    identification facts so the agent asks + confirms them before proceeding. None when
    none are configured (today's default = address only)."""
    from .contract.locale import phrase

    wanted = _cfg().get("extra_questions") or []
    asks = [phrase(f"identification.questions.{q}") for q in wanted if q]
    if not asks:
        return None
    joined = " ".join(f'"{a}"' for a in asks)
    return (
        "- EXTRA VERIFICATION: besides the address, also ask and confirm: "
        + joined
        + " Ask ONE thing at a time and wait; do these before treating the caller as fully "
        "identified."
    )
