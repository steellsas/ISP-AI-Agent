"""Ar žinių paieška sveika — skaičiais, ne nuojauta (RAG planas, E4).

Kam atskiras modulis: iki šiol apie paiešką žinojom tik tada, kai kas nors sugesdavo per skambutį.
Eksploatacijai reikia atsakymų į keturis klausimus, ir visi jie turi būti pigūs:

    ar indeksas ŠVIEŽUS      `drift` — kuo indeksas skiriasi nuo failų
    ar jis PAKANKAMAS        atgaminimo patikra prieš tą patį klausimų rinkinį
    ar modelis TAS PATS      indekse įrašytas modelis prieš tą, kuriuo koduojam dabar
    ar paieška NEDŪSTA       kiek užklausų, kiek nusileidimų, kokia p95

Paskutinis punktas yra tas, kurio negalima sužinoti iš failų: nusileidimai (į leksinę pusę, į failus)
yra tylūs pagal sumanymą — skambutis nenutrūksta. Bet jei jų dalis auga, vadinasi kažkas nebeveikia,
ir tai turi pasimatyti prieš tai, kai pasimatys kokybėje.

Skaitliukai gyvena procese ir yra sąmoningai paprasti: jokios telemetrijos priklausomybės, jokio
rašymo į diską. Kas nori istorijos — nuskaito juos periodiškai (`--check` CLI) ir įrašo pas save.
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Counters:
    """Ką paieška padarė šiame procese. Vienas užraktas, jokių lenktynių tarp gijų."""

    searches: int = 0
    lexical_only: int = 0  # semantinės pusės nebuvo (nėra modelio, nesulaukė, nesutapo)
    store_failures: int = 0  # saugykla neatsakė — nusileidom į failus
    refusals: dict[str, int] = field(default_factory=dict)  # vartų atsisakymai pagal priežastį
    model_mismatch: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def searched(self, ms: float, *, lexical_only: bool) -> None:
        with self._lock:
            self.searches += 1
            self.lexical_only += bool(lexical_only)
            # Paskutinės 500 užklausų: p95 turi rodyti DABAR, ne visą proceso istoriją.
            self.latencies_ms.append(ms)
            if len(self.latencies_ms) > 500:
                del self.latencies_ms[:-500]

    def refused(self, why: str) -> None:
        with self._lock:
            self.refusals[why] = self.refusals.get(why, 0) + 1

    def store_failed(self) -> None:
        with self._lock:
            self.store_failures += 1

    def mismatched(self) -> None:
        with self._lock:
            self.model_mismatch += 1

    def reset(self) -> None:
        """Nunulina skaitliukus.

        Eksploatacijai tai naudinga: nuskaitei ir nunulinai — tada rodikliai rodo INTERVALĄ, ne visą
        proceso istoriją, o senas incidentas nebeslepia šviežio. Testams tai reikalinga, nes
        skaitliukai vieni visam procesui.
        """
        with self._lock:
            self.searches = 0
            self.lexical_only = 0
            self.store_failures = 0
            self.model_mismatch = 0
            self.refusals.clear()
            self.latencies_ms.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = sorted(self.latencies_ms)
        p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0.0
        return {
            "searches": self.searches,
            "lexical_only": self.lexical_only,
            "lexical_only_share": (self.lexical_only / self.searches) if self.searches else 0.0,
            "store_failures": self.store_failures,
            "model_mismatch": self.model_mismatch,
            "refusals": dict(self.refusals),
            "median_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
            "p95_ms": round(p95, 1),
        }


counters = Counters()


class timed:
    """`with timed():` — viena paieška, jos laikas ir ar semantinė pusė dalyvavo."""

    def __init__(self) -> None:
        self.lexical_only = True
        self._started = 0.0

    def __enter__(self) -> timed:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *_exc: Any) -> None:
        counters.searched(
            (time.perf_counter() - self._started) * 1000, lexical_only=self.lexical_only
        )


@dataclass(frozen=True)
class Health:
    """Paieškos būklė vienu atsakymu. `alarms` tuščias reiškia „viskas gerai"."""

    backend: str
    collection: str | None
    points: int
    index_model: str
    serving_model: str
    drift: dict[str, str]
    recall: Any | None
    stats: dict[str, Any]
    alarms: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.alarms


# Kada rėkiam. Ribos sąmoningai atlaidžios: aliarmas, kuris kartojasi be reikalo, nustojamas skaityti.
MAX_LEXICAL_ONLY_SHARE = 0.25
MAX_P95_MS = 150.0


def check(
    *,
    qdrant: Any | None = None,
    max_lexical_only: float = MAX_LEXICAL_ONLY_SHARE,
    max_p95_ms: float = MAX_P95_MS,
) -> Health:
    """Viena patikra visiems keturiems klausimams. Skirta `--check` komandai ir cron'ui.

    `qdrant` paduodamas iš išorės (testai, vietinis režimas); be jo klientas sukuriamas iš aplinkos.
    Patikra, kurios negalima patikrinti, yra tokia pat gera, kaip jos nebuvimas.
    """
    from agent import knowledge_base as kb

    from . import embed
    from .qdrant_store import KnowledgeIndex, QdrantRetriever, client
    from .questions import passes

    backend = kb.backend()
    stats = counters.snapshot()
    alarms: list[str] = []

    collection: str | None = None
    points = 0
    index_model = ""
    drift: dict[str, str] = {}
    recall = None

    if backend is None:
        # Failų kelias: indekso nėra, tad tikrinam tik atgaminimą.
        from .lexical import LexicalRetriever

        ok, recall = passes(LexicalRetriever())
        if not ok:
            alarms.append(f"atgaminimas per failus per žemas: {recall}")
    else:
        index = KnowledgeIndex(
            qdrant or client(), getattr(backend, "collection", None) or kb_alias()
        )
        try:
            collection = index.current()
            if collection is None:
                alarms.append("indekso nėra: aliasas niekur nerodo")
            else:
                points = index.qdrant.count(collection).count
                index_model = index.model()
                drift = index.drift()
                if drift:
                    alarms.append(f"indeksas skiriasi nuo failų: {drift}")
                if not points:
                    alarms.append(f"{collection}: nulis taškų")
                ok, recall = passes(QdrantRetriever(index.qdrant, collection))
                if not ok:
                    alarms.append(f"atgaminimas per indeksą per žemas: {recall}")
        except Exception as exc:
            alarms.append(f"saugykla neatsako: {exc}")

    serving = embed.MODEL if embed.embedder() is not None else ""
    if index_model and serving and index_model != serving:
        alarms.append(f"modelis nesutampa: indeksas '{index_model}', aptarnaujam '{serving}'")
    if stats["searches"] and stats["lexical_only_share"] > max_lexical_only:
        alarms.append(
            f"nusileidimų į leksinę pusę dalis {stats['lexical_only_share']:.0%} "
            f"(riba {max_lexical_only:.0%}) — modelis ar servisas dūsta"
        )
    if stats["p95_ms"] > max_p95_ms:
        alarms.append(f"paieškos p95 {stats['p95_ms']:.0f}ms (riba {max_p95_ms:.0f}ms)")
    if stats["store_failures"]:
        alarms.append(f"saugykla neatsakė {stats['store_failures']} kartus — dirbta iš failų")

    return Health(
        backend=getattr(backend, "name", "files"),
        collection=collection,
        points=points,
        index_model=index_model,
        serving_model=serving,
        drift=drift,
        recall=recall,
        stats=stats,
        alarms=tuple(alarms),
    )


def kb_alias() -> str:
    from .qdrant_store import ALIAS

    return ALIAS
