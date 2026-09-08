"""
Klausimų registras — B bangos pamatas (Andrius 2026-09-07): universalus
dialogo variklis, kuriame PASKUTINIS užduotas klausimas turi VIENĄ savininką,
o kiekvienas kliento turn'as pirmiausia vertinamas prieš TĄ klausimą
(atsakyta / dalinai / neaišku → tikslinam / nukrypimas → grąžinam į kelią).

Žingsnis 1 (shadow): registras ATSPINDI realybę — klausimo savininkai jį
pildo, skaitytuvai valo, trace rodo `question` įvykius. Elgsenos jis dar
nekeičia: maršrutizacija lieka esamoms vėliavoms (_reopen_confirm_pending,
_cannot_now_state, ticket_stage…). Žingsniai 2–4 po vieną migruoja
identifikacijos, tiketo ir walker'io klausimus, kol registras tampa
vieninteliu šaltiniu ir prioritetų teisėju (saugiklis > aktyvus tikslinimas >
stadijos savininkas > šalutinė tema).

Savininkai: "safety" (reopen_confirm, cannot_now…), "ident" (adresas, butas,
vardas, kodas), "ticket" (numeris, valandos), "walker" (įrodymai/žingsniai).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Prioritetų tvarka daugiasignaliam turn'ui (gyva P6 2026-09-07: „negaliu
# dabar" + „ne namuose" + adreso klausimas viename turn'e) — mažesnis
# skaičius laimi.
OWNER_PRIORITY = {"safety": 0, "ident": 1, "ticket": 2, "walker": 3}


@dataclass
class ActiveQuestion:
    """Vienas užduotas klausimas: kas klausė, ko ir kelintą kartą."""

    owner: str  # "safety" | "ident" | "ticket" | "walker"
    key: str  # pvz. "reopen_confirm", "cannot_now_clarify", "ticket_phone"
    asks: int = 1  # kelintas to paties klausimo bandymas (tikslinimo riba)
    data: dict[str, Any] = field(default_factory=dict)  # savininko kontekstas


def register(engine: Any, owner: str, key: str, **data: Any) -> ActiveQuestion:
    """Klausimo savininkas skelbia: ŠIS klausimas dabar valdo turn'ą.
    Pakartotinis tas pats klausimas kelia asks skaitiklį (tikslinimo ribai)."""
    prev = getattr(engine, "_active_question", None)
    q = ActiveQuestion(owner=owner, key=key, data=data)
    if prev is not None and prev.owner == owner and prev.key == key:
        q.asks = prev.asks + 1
    engine._active_question = q
    engine.tracer.emit("question", owner=owner, key=key, asks=q.asks)
    return q


def active(engine: Any) -> ActiveQuestion | None:
    return getattr(engine, "_active_question", None)


def clear(engine: Any, key: str | None = None) -> None:
    """Atsakymas perskaitytas (ar klausimas nurašytas) — registras valomas.
    Su `key` valoma tik jei aktyvus būtent tas klausimas (svetimo nelietiam)."""
    q = getattr(engine, "_active_question", None)
    if q is None:
        return
    if key is not None and q.key != key:
        return
    engine._active_question = None
    engine.tracer.emit("question", owner=q.owner, key=q.key, asks=q.asks, action="closed")
