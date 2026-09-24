"""Žinių indeksas Qdrant'e: ingestija, versijos per aliasą, paieška (RAG planas, E2).

E2 sąmoningai be embedding'ų. Priežastis: DB kelias — transakcijos, filtrai, aliasai, perindeksavimas
serveriui dirbant — įrodomas anksčiau, nei atsiranda modelis. Jei kas nors ne taip su ingestija, tai
išaiškėja be embedding'ų sluoksnio, o ne per skambutį.

Kas čia yra:

    KnowledgeIndex   failai -> Qdrant. Ne skambučio metu. Perkūrimas per NAUJĄ kolekciją ir aliaso
                     perjungimą, tad paieška nė sekundės nemato pusiau užpildyto indekso.
    QdrantRetriever  `RetrieverPort` per Qdrant. Tie patys trys atsakymo lygiai ir tie patys filtrai,
                     kaip leksinėje realizacijoje — kitaip dvi saugyklos atsakytų nevienodai.

Versija yra KOLEKCIJOS vardas: `kb_v3`, o `kb` yra tik aliasas. Iš to seka viskas, ko reikia
eksploatacijai: perkūrimas fone, kanarėlė prieš perjungimą, atstatymas atgal viena operacija.

Tiesos šaltinis lieka markdown failai. Qdrant yra IŠVESTINIS indeksas — jo galima nebeturėti, ir
agentas vis tiek turės žinias (`LexicalRetriever`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any

from agent import knowledge_base as kb

from .sparse import for_chunk, for_query

logger = logging.getLogger(__name__)

ALIAS = os.getenv("KB_COLLECTION", "kb")
SPARSE_VECTOR = "lt_sparse"

# Payload laukai, pagal kuriuos FILTRUOJAMA. Jiems kuriami indeksai: filtras turi veikti paieškos
# metu, ne po jos — kitaip atrenkam dvidešimt, o filtras palieka du (klasikinė post-filtravimo bėda).
INDEXED_FIELDS = ("source", "kind", "tags", "equipment", "problem", "problem_family")

# Taškų ID erdvė: uuid5 iš (šaltinis, dalies numeris). Tas pats dokumentas, indeksuotas du kartus,
# perrašo tuos pačius taškus — ingestija idempotentiška.
_NAMESPACE = uuid.UUID("6f9c2a1e-0d2b-4c51-9a3f-2b7e5d8c1a44")


def point_id(source: str, ord_: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{source}#{ord_}"))


def content_hash(doc: dict[str, Any]) -> str:
    """Dokumento turinio maiša — pagal ją perindeksuojamas TIK tas, kuris pasikeitė."""
    payload = "\u0000".join(
        (
            doc["title"],
            doc["kind"],
            *doc["tags"],
            *doc["keywords"],
            *doc["equipment"],
            *doc["problem"],
            doc["body"],
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def families(problems: tuple[str, ...]) -> list[str]:
    """`internet_down` -> `internet`. Šeima skaičiuojama INDEKSUOJANT, kad filtras būtų tikslus
    sutapimas, o ne teksto paieška: kortelė pasako paslaugą (`internet`), dokumentai — tikslią
    problemą."""
    return sorted({problem.split("_")[0] for problem in problems})


def chunks(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Dokumentas taškais: viena markdown dalis = vienas taškas su savo payload."""
    digest = content_hash(doc)
    out: list[dict[str, Any]] = []
    for ord_, section in enumerate(kb._sections(doc)):
        heading, text = section
        out.append(
            {
                "id": point_id(doc["source"], ord_),
                "sparse": for_chunk(doc, section),
                "payload": {
                    "source": doc["source"],
                    "title": doc["title"],
                    "kind": doc["kind"],
                    "tags": list(doc["tags"]),
                    "keywords": list(doc["keywords"]),
                    "equipment": list(doc["equipment"]),
                    "problem": list(doc["problem"]),
                    "problem_family": families(doc["problem"]),
                    "section": heading,
                    "ord": ord_,
                    # Tekstas jau paruoštas KALBAI: be markdown, be emoji, lentelės — sakiniais.
                    "text": kb._speakable(text)[:700],
                    "is_step": bool(kb._STEP_HEADING.match(heading)),
                    "content_hash": digest,
                },
            }
        )
    return out


def client(url: str | None = None, api_key: str | None = None, path: str | None = None):
    """Qdrant klientas. `path=":memory:"` — vietinis režimas testams ir CI (be serverio).

    Gamyboje agentas gauna TIK skaitymo raktą (`QDRANT_READ_KEY`); rašo tik ingestija su
    `QDRANT_API_KEY`. Net jei per LLM kelią kas nors bandytų rašyti į žinių bazę, techniškai
    neturi kuo.

    Numatytas adresas yra `127.0.0.1`, o ne `localhost` — ir tai ne stiliaus klausimas. Išmatuota
    (2026-09-24, Windows): per `localhost` viena užklausa užtrunka **2056 ms**, per `127.0.0.1` —
    **13 ms**. Skirtumas 150 kartų, nes `localhost` pirma bando IPv6 `::1`, kur portas neatidarytas,
    ir laukia baigties. Balso skambutyje tai būtų atrodę kaip „paieška lėta", o kaltas būtų buvęs
    indeksas.

    Transportas — REST. gRPC su ALIASU neveikia (patikrinta 1.19.1: „Collection `kb` doesn't
    exist"), o aliasas yra mūsų versijavimo pagrindas. REST duoda p95 16 ms — su atsarga iki SLO.
    """
    from qdrant_client import QdrantClient

    if path:
        return QdrantClient(path) if path == ":memory:" else QdrantClient(path=path)
    return QdrantClient(
        url=url or os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        api_key=api_key or os.getenv("QDRANT_API_KEY") or os.getenv("QDRANT_READ_KEY"),
        timeout=float(os.getenv("QDRANT_TIMEOUT", "3")),
    )


# --- ingestija ---------------------------------------------------------------------------


@dataclass
class KnowledgeIndex:
    """Failai -> Qdrant. Viskas, kas rašo, yra čia; paieška nerašo niekada."""

    qdrant: Any
    alias: str = ALIAS

    # --- versijos ---

    def current(self) -> str | None:
        """Kolekcija, į kurią rodo aliasas, arba None, jei indekso dar nėra."""
        for record in self.qdrant.get_aliases().aliases:
            if record.alias_name == self.alias:
                return record.collection_name
        return None

    def version(self) -> int:
        name = self.current() or ""
        found = re.search(r"_v(\d+)$", name)
        return int(found.group(1)) if found else 0

    # --- kūrimas ---

    def _create(self, collection: str) -> None:
        from qdrant_client import models

        self.qdrant.create_collection(
            collection,
            vectors_config={},
            sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams()},
        )
        for field in INDEXED_FIELDS:
            # `wait=False`: indeksas sukuriamas fone. Su numatytu `wait=True` šeši laukai kainavo
            # 17,5 s (kiekvieno optimizatoriaus pabaigos laukimas), o tie indeksai reikalingi tik
            # paieškai, kuri prie šios kolekcijos prieis tik po aliaso perjungimo.
            self.qdrant.create_payload_index(
                collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=False,
            )

    def _points(self, docs) -> list[Any]:
        from qdrant_client import models

        return [
            models.PointStruct(
                id=chunk["id"],
                payload=chunk["payload"],
                vector={
                    SPARSE_VECTOR: models.SparseVector(
                        indices=list(chunk["sparse"].indices), values=list(chunk["sparse"].values)
                    )
                },
            )
            for doc in docs
            for chunk in chunks(doc)
        ]

    def rebuild(self, canary=None) -> str:
        """Visas indeksas iš naujo — į NAUJĄ kolekciją, ir tik tada aliasas.

        `canary(collection)` yra patikra prieš perjungimą (atgaminimo testas prieš naują indeksą).
        Jei ji grąžina netiesą, aliasas nejudinamas ir naujoji kolekcija ištrinama: gamyboje lieka
        senas, veikiantis indeksas.
        """
        from qdrant_client import models

        target = f"{self.alias}_v{self.version() + 1}"
        if self.qdrant.collection_exists(target):  # pragma: no cover - nepilnas ankstesnis bandymas
            self.qdrant.delete_collection(target)
        self._create(target)
        points = self._points(kb.documents())
        self.qdrant.upsert(target, points=points, wait=True)
        if canary is not None and not canary(target):
            self.qdrant.delete_collection(target)
            raise RuntimeError(f"canary refused {target}: alias {self.alias} left untouched")
        previous = self.current()
        self.qdrant.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(collection_name=target, alias_name=self.alias)
                )
            ]
        )
        logger.info(f"[KB] alias {self.alias} -> {target} ({len(points)} chunks)")
        return previous or target

    # --- vieno dokumento atnaujinimas ---

    def upsert_document(self, source: str) -> int:
        """Vienas dokumentas: naujos dalys įrašomos, pasenusios ištrinamos.

        Kaina proporcinga PAKEITIMUI, ne bazei. Ir paieška nemato pusės dokumento: senos dalys
        ištrinamos tik po to, kai naujos jau įrašytos.
        """
        from qdrant_client import models

        collection = self._require()
        doc = kb.document(source)
        if doc is None:
            raise KeyError(f"no knowledge document '{source}'")
        fresh = chunks(doc)
        self.qdrant.upsert(collection, points=self._points([doc]), wait=True)
        self.qdrant.delete(
            collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source", match=models.MatchValue(value=doc["source"])
                        ),
                        models.FieldCondition(key="ord", range=models.Range(gte=len(fresh))),
                    ]
                )
            ),
            wait=True,
        )
        return len(fresh)

    def remove_document(self, source: str) -> None:
        """Ištrintas dokumentas nunešamas su visomis dalimis — be liekanų indekse."""
        from qdrant_client import models

        self.qdrant.delete(
            self._require(),
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(key="source", match=models.MatchValue(value=source))
                    ]
                )
            ),
            wait=True,
        )

    # --- būklė ---

    def indexed(self) -> dict[str, str]:
        """{dokumentas: turinio maiša}, kaip jį mato INDEKSAS."""
        out: dict[str, str] = {}
        offset = None
        while True:
            records, offset = self.qdrant.scroll(
                self._require(), limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            for record in records:
                out[record.payload["source"]] = record.payload["content_hash"]
            if offset is None:
                return out

    def drift(self) -> dict[str, str]:
        """Kuo indeksas skiriasi nuo failų: `added`, `changed`, `removed`.

        Tai atsakymas į klausimą „ar indeksas šviežias" — be jo pasenęs indeksas tyliai aptarnautų
        skambučius (taip jau buvo su v1 FAISS indeksu: 2026-06-12 indeksas prieš 2026-09-23
        dokumentus).
        """
        indexed = self.indexed()
        files = {doc["source"]: content_hash(doc) for doc in kb.documents()}
        out = {}
        for source in sorted(set(files) | set(indexed)):
            if source not in indexed:
                out[source] = "added"
            elif source not in files:
                out[source] = "removed"
            elif files[source] != indexed[source]:
                out[source] = "changed"
        return out

    def _require(self) -> str:
        collection = self.current()
        if collection is None:
            raise RuntimeError(f"no knowledge index behind alias '{self.alias}' — build it first")
        return collection


# --- paieška -----------------------------------------------------------------------------


def _filter(where: dict[str, Any]):
    """Filtras, kurio semantika TOKIA PAT, kaip `knowledge_base._matches`.

    Svarbiausia dalis — neutralūs dokumentai. Dokumentas, kuris nedeklaruoja įrangos ar problemos,
    praleidžiamas VISADA: klientas gali paklausti apie lemputę ar meistro kainą interneto gedimo
    viduryje. Qdrant'e tai `should`: arba sutampa, arba laukas tuščias.
    """
    from qdrant_client import models

    must: list[Any] = []
    kind = where.get("kind")
    if kind:
        must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=str(kind))))
    tags = where.get("tags")
    if tags:
        wanted = [tags] if isinstance(tags, str) else list(tags)
        must.append(models.FieldCondition(key="tags", match=models.MatchAny(any=wanted)))
    for field, value in (("equipment", where.get("equipment")), ("problem", where.get("problem"))):
        if not value:
            continue
        asked = str(value).lower()
        # `problem` gali būti tiksli problema (`internet_down`) arba šeima (`internet`) — tą patį
        # daro `_same_problem`, tik ten prefiksu, o čia iš anksto suskaičiuotu `problem_family`.
        key = "problem_family" if field == "problem" and "_" not in asked else field
        must.append(
            models.Filter(
                should=[
                    models.FieldCondition(key=key, match=models.MatchAny(any=[asked])),
                    models.IsEmptyCondition(is_empty=models.PayloadField(key=field)),
                ]
            )
        )
    return models.Filter(must=must) if must else None


@dataclass
class QdrantRetriever:
    """`RetrieverPort` per Qdrant: *sparse* (leksinė) pusė, E3 pridės `dense`."""

    qdrant: Any
    collection: str = ALIAS
    name: str = "qdrant"

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        filter_metadata: dict | None = None,
    ) -> list[dict[str, Any]]:
        from qdrant_client import models

        vector = for_query(query)
        if not vector.indices:
            return []
        floor = kb.FLOOR if threshold is None else threshold
        found = self.qdrant.query_points(
            self.collection,
            query=models.SparseVector(indices=list(vector.indices), values=list(vector.values)),
            using=SPARSE_VECTOR,
            query_filter=_filter(filter_metadata or {}),
            # Žemiau `HINT` nieko nesakom: tai sąžiningas „nežinau", ne tyla dėl per aukštos ribos.
            score_threshold=kb.HINT,
            # Kandidatų imam daugiau, nei grąžinsim: failų realizacija skirsto į lygius peržiūrėjusi
            # VISUS radinius, ir jei pirmas yra spėjimas, o antras tvirtas — grąžina tvirtą. Be šios
            # atsargos dvi saugyklos atsakytų nevienodai į tą patį klausimą.
            limit=max(top_k or 2, 2) * 5,
            with_payload=True,
        ).points
        # Lygių balų tvarka: ta pati, kaip `find()` — pagal šaltinį, tada dalies numerį. Qdrant
        # sparse svorius laiko float32, tad artimi balai kitaip apvalinami; be aiškios tvarkos
        # rezultatai skirtųsi be jokios priežasties.
        found = sorted(found, key=lambda p: (-p.score, p.payload["source"], p.payload["ord"]))
        sure = [point for point in found if point.score >= floor]
        # Trys lygiai, tie patys kaip failų realizacijoje: tvirtas atsakymas, VIENAS pažymėtas
        # spėjimas, arba nieko.
        chosen = sure[: top_k or 2] if sure else found[:1]
        return [
            {
                "document": point.payload["text"],
                "score": round(point.score, 3),
                "id": str(point.id),
                "metadata": {
                    "source": point.payload["source"],
                    "section": point.payload["section"],
                    "kind": point.payload["kind"],
                    "tags": point.payload["tags"],
                    "equipment": point.payload["equipment"],
                    "sure": point.score >= floor,
                },
            }
            for point in chosen
        ]

    def is_loaded(self) -> bool:
        try:
            return self.qdrant.count(self.collection).count > 0
        except Exception as exc:  # pragma: no cover - serveris gali neatsakyti
            logger.warning(f"[KB] qdrant unreachable: {exc}")
            return False

    def load(self, name: str = "default") -> bool:
        return self.is_loaded()

    def save(self, name: str = "default") -> None:
        """Paieška nerašo. Indeksą stato `KnowledgeIndex` — ne skambučio metu."""
