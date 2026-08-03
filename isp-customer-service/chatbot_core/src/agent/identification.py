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
    "ask_caller": True,
    "extra_questions": [],
    "questions": {},
}

_CALLER_QUESTION_DEFAULT = "O su kuo kalbu — koks jūsų vardas? Ar jūs sutartį sudaręs asmuo?"


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


def ask_caller() -> bool:
    """Ask WHO is calling (name + relation to the contract) once the address is
    confirmed — for the call record and identification confidence, never a gate."""
    return bool(_cfg().get("ask_caller", True))


def caller_question() -> str:
    q = (_cfg().get("questions") or {}).get("caller")
    return str(q) if q else _CALLER_QUESTION_DEFAULT


# Scripted identification phrases — engine-composed replies (see the yaml note).
_PHRASES_DEFAULTS: dict[str, str] = {
    "anamnesis_question": (
        "Supratau. O kada pastebėjote, kad dingo internetas — gal po ko nors, "
        "pavyzdžiui, audros ar remonto?"
    ),
    "address_offer": "Ačiū. Kad galėčiau patikrinti situaciją, ar skambinate dėl {adresas}?",
    "address_ask": (
        "Ačiū. Kad galėčiau patikrinti situaciją iš tiekėjo pusės, pasakykite adresą, "
        "kuriuo neveikia internetas."
    ),
    "echo_address": "Supratau — {adresas}.",
    "check_result": "Patikrinau ryšį iki jūsų buto. {zinia}",
    "billing_extra": "Apmokėjus sąskaitą, paslauga bus įjungta.",
    "anything_else": "Ar dar kuo galiu padėti?",
    "thanks": "Ačiū!",
    "confirm_end": (
        "Ar tikrai norite baigti pokalbį? Jei norite, galiu užregistruoti gedimą, "
        "kad kolegos su jumis susisiektų."
    ),
    "goodbye": "Ačiū, kad paskambinote. Geros dienos!",
}


def phrase(key: str, **fmt: str) -> str:
    """A scripted identification phrase (file first, code default), with the
    {placeholders} filled. Unknown key returns '' (fail-soft)."""
    raw = (_cfg().get("phrases") or {}).get(key) or _PHRASES_DEFAULTS.get(key, "")
    try:
        return str(raw).format(**fmt)
    except Exception:  # a bad placeholder edit must not break the call
        return str(raw)


_RELATION_MARKS: dict[str, tuple[str, ...]] = {
    "holder": ("sutart", "savinink", "mano vardu", "aš sudariau", "as sudariau"),
    "family": (
        "vyras",
        "žmona",
        "zmona",
        "vaikas",
        "sūnus",
        "sunus",
        "dukt",
        "dukra",
        "mama",
        "tėv",
        "tev",
        "brolis",
        "sesuo",
        "šeim",
        "seim",
    ),
    "tenant": ("nuominink", "nuomoju", "nuomuoju"),
    "helper": ("kaimyn", "padedu", "padėti", "padeti", "draug"),
}


def detect_caller_relation(text: str | None) -> str:
    """Keyword-read the caller's relation to the contract from their intro. Record
    + confidence signal only — never a gate."""
    if not text:
        return "unknown"
    low = text.lower()
    # Relation words WIN over a contract mention: "žmona sutartį sudariusio" names the
    # HOLDER'S wife — the caller is family, even though "sutart..." appears.
    for rel in ("family", "tenant", "helper"):
        if any(m in low for m in _RELATION_MARKS[rel]):
            return rel
    if any(m in low for m in ("ne sutart", "nesu sudar", "ne aš sudar", "ne as sudar")):
        return "other"  # explicitly not the holder, relation unstated
    if any(m in low for m in _RELATION_MARKS["holder"]):
        return "holder"
    if any(m in low for m in ("taip", "aš", "as ")):
        return "holder"  # a plain yes to "ar jūs sutartį sudaręs asmuo?"
    return "unknown"


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
