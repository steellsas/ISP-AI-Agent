"""Facts the caller says in passing, whatever we asked (Andrius, 2026-11-05).

„Telefone neveikia internetas" answers which device fails even when the question out was
about the other devices — and the complaint itself („neveikia internetas telefone") already
says it. Live 2026-11-05 nothing read it: the device was asked twice more, the caller answered
„neturiu", and the call ended in a ticket with nothing checked.

Only the needs a card marks `heard_anytime` are read this way, and a clause that says the
thing WORKS („kompiuteryje veikia") never names the device that fails.
"""

from __future__ import annotations

import re
from typing import Any

from .. import ledger
from ..contract import cards as catalog
from ..contract.locale import vocab

_CLAUSES = re.compile(r"[,.;!?]|\s(?:o|bet|ir|tik ne)\s", re.IGNORECASE)


def failing_part(text: str) -> str:
    """The clauses that do not say something works."""
    kept = []
    for clause in _CLAUSES.split(text or ""):
        low = clause.lower()
        if any(m in low for m in vocab("works_marks")) and not any(
            m in low for m in vocab("fails_marks")
        ):
            continue
        kept.append(clause)
    return " ".join(kept).strip()


def hear_in_passing(state: Any, rt: Any) -> None:
    if state.ticket.stage or not state.dialog.last_heard:
        return
    from ..evidence import read_pending_answer, spec_for

    heard = failing_part(state.dialog.last_heard)
    if not heard:
        return
    for card in catalog.cards().values():
        client = (spec_for(card.fault) or {}).get("client") or {}
        for fact, need in card.needs.items():
            if not need.heard_anytime:
                continue
            if fact in state.case.facts and fact not in state.case.assumed:
                continue
            value = read_pending_answer(fact, heard, client.get(fact))
            if value and ledger.record_client(state, rt, fact, value):
                state.case.assumed.pop(fact, None)
                state.case.unavailable = [f for f in state.case.unavailable if f != fact]
                rt.tracer.emit("facts", source="in_passing", fact=fact, value=value)
