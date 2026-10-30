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
    for stem, label in vocab_map("payment_methods").items():
        if stem in low:
            found["how"] = label
            break
    return found


def _when(low: str) -> str | None:
    """A month („liepą", „liepos 10 d.") or a relative day („vakar", „prieš savaitę")."""
    for stem, month in vocab_map("payment_months").items():
        m = re.search(rf"\b{stem}\w*(?:\s+(\d{{1,2}})(?:\s*d\.?)?)?", low)
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
