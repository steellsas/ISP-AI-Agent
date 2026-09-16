"""
Inform packages (closing wave, Andrius 2026-09-08): what the caller HEARS on
an inform verdict (debt, outage) lives in knowledge/inform.yaml — a
file edit, not code. This module is only the mechanics: load the catalog,
build the placeholder values from the diagnose signals, and render the
template with the drop-a-sentence rule (a sentence whose placeholder has no
value is silently omitted — the agent never speaks a lie or an empty blank).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .contract.locale import lang

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent / "knowledge" / "inform.yaml"


def _catalog() -> dict:
    from .contract.loader import read_yaml

    return read_yaml(_PATH) or {}


def reload() -> None:
    """Nothing derived to drop — the catalog is read_yaml's cache."""


def _values(state: Any, rt: Any, reason: str) -> dict[str, str]:
    """Placeholder values from the diagnose signals — only the ones that
    genuinely exist; the renderer drops sentences for the missing ones."""
    signals = ((state.diagnosis.verdicts.get("network") or {}).get("signals")) or {}
    vals: dict[str, str] = {}
    from .faults import verdict_flag

    kind = verdict_flag(reason, "inform")
    if kind == "debt":
        debt = signals.get("billing_debt") or {}
        if debt.get("amount"):
            vals["amount"] = lang().money(float(debt["amount"]))
        m = lang().months(debt.get("months") or [])
        if m:
            vals["months"] = m
        lp = lang().date(debt.get("last_payment"))
        if lp:
            vals["last_payment"] = lp
    elif kind == "service":
        from .intents import intent_service

        service = intent_service(state.intake.problem_type)
        if service:
            from .contract.locale import phrase_or

            label = phrase_or(f"service_label.{service}", "")
            if label:
                vals["service"] = label
    elif kind == "outage":
        incident = signals.get("incident") or {}
        if incident.get("description"):
            vals["location"] = str(incident["description"])
        eta = str(incident.get("estimated_resolution") or "")
        if len(eta) >= 16:
            vals["eta"] = eta[11:16]  # HH:MM, voice-friendly
        elif eta:
            vals["eta"] = eta
    return vals


def clarity_declaration(reason: str | None) -> list[str] | None:
    """The declared clarity requirements for a verdict — what the caller must
    know before the goodbye (what_is_wrong / what_to_do / what_is_being_done /
    when_restored / how_notified).
    The wrap-up traces it on close; block-2+ enforcement reads it."""
    if not reason:
        return None
    entry = _catalog().get(reason)
    if not isinstance(entry, dict):
        return None
    required = entry.get("clarity_requirements")
    return list(required) if isinstance(required, list) else None


def inform_text(state: Any, rt: Any, reason: str | None) -> str | None:
    """The rendered inform speech for this verdict, or None when no template
    applies (the caller then falls back to the glossary gloss). The
    drop-a-sentence rule: a template sentence whose placeholder has no value
    is omitted; if NO data sentence survives, the entry's `fallback` speaks."""
    if not reason:
        return None
    entry = _catalog().get(reason)
    if not isinstance(entry, dict) or not entry.get("template_key"):
        return None
    from .contract.locale import template

    vals = _values(state, rt, reason)
    sentences = re.split(r"(?<=[.!?])\s+", template(entry["template_key"]).strip())
    kept: list[str] = []
    data_sentences = 0
    placeholder_sentences = 0
    for sent in sentences:
        keys = re.findall(r"\{(\w+)\}", sent)
        if not keys:
            kept.append(sent)
            continue
        placeholder_sentences += 1
        if all(k in vals for k in keys):
            kept.append(sent.format(**vals))
            data_sentences += 1
    # The fallback kicks in only when the template HAS data sentences and none
    # rendered — a fully static template (node/switch fault) speaks as-is.
    if placeholder_sentences and data_sentences == 0:
        fb = template(entry["fallback_key"]).strip() if entry.get("fallback_key") else ""
        return re.sub(r"\s+", " ", fb) if fb else None
    text = re.sub(r"\s+", " ", " ".join(kept)).strip()
    # N4 (live): a value ending in "d." plus the template's own period made
    # "birželio 5 d.." — collapse doubled dots.
    return re.sub(r"\.\.+", ".", text)
