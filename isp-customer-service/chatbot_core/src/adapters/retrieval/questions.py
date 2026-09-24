"""Atgaminimo patikra: ar indeksas atsako į klausimus, kuriuos žinios pažadėjo (RAG planas, E2).

Tas pats rinkinys ir tos pačios ribos, kurias naudoja `tests/test_knowledge_recall.py` — failas
`_questions.yaml` gyvena prie žinių būtent todėl, kad CI ir gamyba niekada nesutartų nevienodai, kas
yra „pakankamai gerai".

Gamyboje tai KANARĖLĖ: paleidžiama prieš naują indeksą ir **prieš** aliaso perjungimą. Nepavyko —
aliasas nejudinamas, skambučius aptarnauja senas, veikiantis indeksas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from agent import knowledge_base as kb


@dataclass(frozen=True)
class Recall:
    """Ką patikra pamatė."""

    hit1: float
    hit2: float
    silent: int
    total: int
    misses: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"hit@1 {self.hit1:.0%} · hit@2 {self.hit2:.0%} · tyla {self.silent} "
            f"(iš {self.total} klausimų)"
        )


def spec() -> dict[str, Any]:
    return yaml.safe_load((kb.KB_DIR / "_questions.yaml").read_text(encoding="utf-8")) or {}


def questions() -> list[tuple[str, tuple[str, ...]]]:
    out: list[tuple[str, tuple[str, ...]]] = []
    for source, asks in (spec().get("documents") or {}).items():
        for ask in asks:
            if isinstance(ask, dict):
                out.append((str(ask["ask"]), (source, *(ask.get("or") or ()))))
            else:
                out.append((str(ask), (source,)))
    return out


def measure(retriever, top_k: int = 2) -> Recall:
    """Paleidžia visą rinkinį per BET KURIĄ porto realizaciją — failus ar Qdrant."""
    asked = questions()
    hit1 = hit2 = silent = 0
    misses: list[str] = []
    for question, accepted in asked:
        found: list[str] = []
        for chunk in retriever.retrieve(question, top_k=top_k):
            source = chunk["metadata"]["source"]
            if source not in found:
                found.append(source)
        if not found:
            silent += 1
        if found[:1] and found[0] in accepted:
            hit1 += 1
        if set(found[:2]) & set(accepted):
            hit2 += 1
        else:
            misses.append(f"{question} -> norėjom {accepted[0]}, gavom {found or 'NIEKO'}")
    total = len(asked) or 1
    return Recall(hit1 / total, hit2 / total, silent, len(asked), tuple(misses))


def passes(retriever) -> tuple[bool, Recall]:
    """Ar indeksas pakankamai geras, kad jį būtų galima duoti skambučiams."""
    # Vardas ne `limits`: projekte `limits.get("…")` yra derinamų ribų registras, ir sutapimas
    # suklaidintų tiek skaitantį, tiek `test_limits.py` skenerį.
    thresholds = spec()
    seen = measure(retriever)
    ok = (
        seen.hit1 >= float(thresholds.get("min_hit1", 0))
        and seen.hit2 >= float(thresholds.get("min_hit2", 0))
        and seen.silent <= int(thresholds.get("max_silent", 0))
    )
    return ok, seen
