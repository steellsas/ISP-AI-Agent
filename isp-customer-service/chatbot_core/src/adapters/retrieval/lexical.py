"""Leksinė paieška per markdown failus, `RetrieverPort` forma (RAG planas, E1).

Kodėl portas atsiranda DABAR, kai saugykla dar viena: kad E2 (Qdrant) būtų adapterio pakeitimas, o
ne agento perrašymas. Ir kad atsarginis kelias būtų tikras — failai yra TIESOS ŠALTINIS, tad ši
realizacija veikia ir tada, kai vektorinė DB neatsako.

Filtras paduodamas `filter_metadata` žodynu (`kind`, `problem`, `equipment`, `tags`) — tie patys
raktai, kurie E2 taps Qdrant payload indeksais.
"""

from __future__ import annotations

from typing import Any

from agent import knowledge_base as kb


class LexicalRetriever:
    """`RetrieverPort` per žinių dokumentus: šaknų sutapimas su IDF svoriais."""

    name = "lexical"

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        filter_metadata: dict | None = None,
    ) -> list[dict[str, Any]]:
        where = filter_metadata or {}
        passages = kb.find(
            query,
            kind=where.get("kind"),
            tags=where.get("tags"),
            equipment=where.get("equipment"),
            problem=where.get("problem"),
            limit=top_k or 2,
            **({"floor": threshold} if threshold is not None else {}),
        )
        return [
            {
                "document": passage.text,
                "score": passage.score,
                "id": f"{passage.source}#{passage.title}",
                "metadata": {
                    "source": passage.source,
                    "section": passage.title,
                    "kind": passage.kind,
                    "tags": list(passage.tags),
                    "equipment": list(passage.equipment),
                    # `sure=False` reiškia „geriausia, ką turiu, bet nesu tikras" — agentas tada
                    # patikslina, o ne improvizuoja. Tai sutarties dalis, ne priedas.
                    "sure": passage.sure,
                },
            }
            for passage in passages
        ]

    def is_loaded(self) -> bool:
        return bool(kb.documents())

    def load(self, name: str = "default") -> bool:
        """Failai yra saugykla, tad „užkrauti" reiškia atmesti kešą."""
        kb.reload()
        return self.is_loaded()

    def save(self, name: str = "default") -> None:
        """Nėra ko išsaugoti: dokumentai gyvena repozitorijoje ir keliauja code review."""
