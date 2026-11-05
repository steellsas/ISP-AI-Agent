"""The caller's payment claim in a debt dispute — when, how and how much they paid.

The responsible person searches for the payment by these details, so the agent asks for the
missing ones and the ticket carries them as the caller said them.
"""

from __future__ import annotations

import re

from ..contract.locale import lang, vocab, vocab_map

PARTS = ("when", "how", "amount")
# The order the agent asks in: the way of paying last — it carries its examples.
ASK_ORDER = ("when", "amount", "how")


def read_payment_claim(text: str | None) -> dict[str, str]:
    """The parts of a payment the caller named in this sentence („liepą, 40 eurų, banku")."""
    if not text:
        return {}
    norm = lang().normalize_numbers(text)
    low = norm.lower()
    found: dict[str, str] = {}
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:eur|€)", low)
    if m:
        found["amount"] = f"{m.group(1).replace('.', ',')} €"
    when = _when(low)
    if when:
        found["when"] = when
    how = _how(low)
    if how:
        found["how"] = how
    return found


def _how(low: str) -> str | None:
    """„pavedimu per Swedbank" → „banko pavedimu, per Swedbank"; a vague „per banką" only alone."""
    named = {s: label for s, label in vocab_map("payment_methods").items() if s in low}
    vague = set(vocab("payment_methods_vague"))
    if any(s not in vague for s in named):
        named = {s: label for s, label in named.items() if s not in vague}
    labels = list(dict.fromkeys(named.values()))
    return ", ".join(labels) or None


def merge_claim(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """A later sentence corrects the date and the sum but adds to the way of paying."""
    merged = {**old, **new}
    before, after = old.get("how"), new.get("how")
    vague = {vocab_map("payment_methods")[s] for s in vocab("payment_methods_vague")}
    if before and after and before not in vague and after not in before:
        merged["how"] = f"{before}, {after}"
    elif before and after and after in before:
        merged["how"] = before
    return merged


def _when(low: str) -> str | None:
    """A month („liepą", „liepos 10 d.") or a relative day („vakar", „prieš savaitę")."""
    for stem, month in vocab_map("payment_months").items():
        # „liepą 40 eur" names the sum, not the 40th day.
        m = re.search(rf"\b{stem}\w*(?:\s+(\d{{1,2}})(?![\d.,]*\s*(?:eur|€))(?:\s*d\.?)?)?", low)
        if m:
            day = m.group(1)
            return f"{month.split()[0]} {day} d." if day else month
    for word in vocab("payment_relative_days"):
        # „prieš savaitę", „praeitą mėnesį" need their next word; „vakar" stands alone.
        tail = r"\s+\w+" if word in vocab("payment_relative_needs_next") else ""
        m = re.search(rf"\b{re.escape(word)}\w*{tail}", low)
        if m:
            return m.group(0).strip()
    return None


def missing_parts(claim: dict[str, str]) -> list[str]:
    return [p for p in ASK_ORDER if not claim.get(p)]
