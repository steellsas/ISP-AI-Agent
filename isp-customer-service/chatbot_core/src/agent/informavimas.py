"""
Inform packages (closing wave, Andrius 2026-09-08): what the caller HEARS on
an inform verdict (debt, outage) lives in knowledge/informavimas.yaml — a
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

logger = logging.getLogger(__name__)

_CATALOG: dict | None = None

# Lithuanian month names: accusative ("skola už liepą") and genitive
# ("birželio 5 d.") — keyed by the two-digit month.
_MONTH_ACC = {
    "01": "sausį", "02": "vasarį", "03": "kovą", "04": "balandį",
    "05": "gegužę", "06": "birželį", "07": "liepą", "08": "rugpjūtį",
    "09": "rugsėjį", "10": "spalį", "11": "lapkritį", "12": "gruodį",
}  # fmt: skip
_MONTH_GEN = {
    "01": "sausio", "02": "vasario", "03": "kovo", "04": "balandžio",
    "05": "gegužės", "06": "birželio", "07": "liepos", "08": "rugpjūčio",
    "09": "rugsėjo", "10": "spalio", "11": "lapkričio", "12": "gruodžio",
}  # fmt: skip


def _catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        try:
            import yaml

            path = Path(__file__).parent / "knowledge" / "informavimas.yaml"
            _CATALOG = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # pragma: no cover - a missing file just disables templates
            logger.warning("informavimas.yaml load failed", exc_info=True)
            _CATALOG = {}
    return _CATALOG


def _eur(amount: float) -> str:
    """TTS-friendly money: 49.98 -> "49 eurai 98 centai" (correct LT forms)."""

    def _form(n: int, one: str, few: str, many: str) -> str:
        if n % 10 == 1 and n % 100 != 11:
            return one
        if 2 <= n % 10 <= 9 and not 11 <= n % 100 <= 19:
            return few
        return many

    eur = int(amount)
    ct = round((amount - eur) * 100)
    text = f"{eur} {_form(eur, 'euras', 'eurai', 'eurų')}"
    if ct:
        text += f" {ct} {_form(ct, 'centas', 'centai', 'centų')}"
    return text


def _months_acc(periods: list[str]) -> str | None:
    """['2026-07','2026-08'] -> "liepą ir rugpjūtį"."""
    names = [_MONTH_ACC.get(p[5:7]) for p in periods if len(p) >= 7]
    names = [n for n in names if n]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " ir " + names[-1]


def _date_gen(date: str | None) -> str | None:
    """'2026-06-05' -> "birželio 5 d."."""
    if not date or len(date) < 10:
        return None
    month = _MONTH_GEN.get(date[5:7])
    try:
        day = int(date[8:10])
    except ValueError:
        return None
    return f"{month} {day} d." if month else None


def _values(engine: Any, reason: str) -> dict[str, str]:
    """Placeholder values from the diagnose signals — only the ones that
    genuinely exist; the renderer drops sentences for the missing ones."""
    signals = ((engine.state.diagnosis.get("network") or {}).get("signals")) or {}
    vals: dict[str, str] = {}
    if reason == "billing_suspended":
        debt = signals.get("billing_debt") or {}
        if debt.get("amount"):
            vals["suma"] = _eur(float(debt["amount"]))
        m = _months_acc(debt.get("months") or [])
        if m:
            vals["menesiai"] = m
        lp = _date_gen(debt.get("last_payment"))
        if lp:
            vals["pask_mokejimas"] = lp
    elif reason == "active_outage":
        incident = signals.get("incident") or {}
        if incident.get("description"):
            vals["vieta"] = str(incident["description"])
        eta = str(incident.get("estimated_resolution") or "")
        if len(eta) >= 16:
            vals["eta"] = eta[11:16]  # HH:MM, voice-friendly
        elif eta:
            vals["eta"] = eta
    return vals


def clarity_declaration(reason: str | None) -> list[str] | None:
    """The declared aiskumo_salyga for a verdict — what the caller must know
    before the goodbye (kas_negerai / ka_daryti / kas_daroma / kada_atsistatys).
    The wrap-up traces it on close; block-2+ enforcement reads it."""
    if not reason:
        return None
    entry = _catalog().get(reason)
    if not isinstance(entry, dict):
        return None
    salyga = entry.get("aiskumo_salyga")
    return list(salyga) if isinstance(salyga, list) else None


def inform_text(engine: Any, reason: str | None) -> str | None:
    """The rendered inform speech for this verdict, or None when no template
    applies (the caller then falls back to the glossary gloss). The
    drop-a-sentence rule: a template sentence whose placeholder has no value
    is omitted; if NO data sentence survives, the entry's `fallback` speaks."""
    if not reason:
        return None
    entry = _catalog().get(reason)
    if not isinstance(entry, dict) or not entry.get("sakoma"):
        return None
    vals = _values(engine, reason)
    sentences = re.split(r"(?<=[.!?])\s+", str(entry["sakoma"]).strip())
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
        fb = str(entry.get("fallback") or "").strip()
        return re.sub(r"\s+", " ", fb) if fb else None
    text = re.sub(r"\s+", " ", " ".join(kept)).strip()
    # N4 (live): a value ending in "d." plus the template's own period made
    # "birželio 5 d.." — collapse doubled dots.
    return re.sub(r"\.\.+", ".", text)
