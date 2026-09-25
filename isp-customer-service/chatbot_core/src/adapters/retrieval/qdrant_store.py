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

from . import embed
from .sparse import Sparse, for_body, for_chunk, for_query

logger = logging.getLogger(__name__)

ALIAS = os.getenv("KB_COLLECTION", "kb")
SPARSE_VECTOR = "lt_sparse"
# Ta pati dalis be dokumento paviršiaus — lygių balų skirtukas, kad Qdrant ir failai rikiuotų
# vienodai (žr. `sparse.for_body`).
BODY_VECTOR = "lt_body"
DENSE_VECTOR = "dense"

# Kiek kandidatų atrenka kiekviena hibrido pusė prieš sujungimą. Plati atranka + tikslus rikiavimas:
# išmatuota, kad būtent tokia grandinė laikosi bazei augant (RAG_SPRENDIMAI.md 7.2).
PREFETCH = int(os.getenv("KB_PREFETCH", "20"))

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


def chunks(
    doc: dict[str, Any], vectors: dict[str, list[float]] | None = None
) -> list[dict[str, Any]]:
    """Dokumentas taškais: viena markdown dalis = vienas taškas su savo payload.

    `vectors` — jau suskaičiuoti `dense` vektoriai pagal dalies tekstą (indeksuojant jie
    skaičiuojami paketu, ne po vieną). Be jų taškas turi tik *sparse* pusę, ir tai teisėta būklė:
    E2 indeksas be modelio veikia toliau.
    """
    digest = content_hash(doc)
    out: list[dict[str, Any]] = []
    for ord_, section in enumerate(kb._sections(doc)):
        heading, text = section
        out.append(
            {
                "id": point_id(doc["source"], ord_),
                "sparse": for_chunk(doc, section),
                "body": for_body(doc, section),
                "dense": (vectors or {}).get(f"{doc['source']}#{ord_}"),
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
                    # Kuris modelis suskaičiavo `dense`. Nesutampa — neaptarnaujam, o ne tyliai
                    # klystam: kito modelio vektoriai kitoje erdvėje reiškia atsitiktinį rikiavimą.
                    "model": embed.MODEL if (vectors or {}).get(f"{doc['source']}#{ord_}") else "",
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
            # `dense` vieta paruošiama VISADA, net kai modelio nėra: taip E2 indeksą galima
            # praturtinti embedding'ais nekeičiant kolekcijos formos (E3).
            vectors_config={
                DENSE_VECTOR: models.VectorParams(size=embed.DIM, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                SPARSE_VECTOR: models.SparseVectorParams(),
                BODY_VECTOR: models.SparseVectorParams(),
            },
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

    def _dense(self, docs) -> dict[str, list[float]]:
        """`dense` vektoriai visoms dalims — vienu paketu, ne po vieną.

        Modelio nėra arba jis neatsako: grąžinam tuščia, ir indeksas statomas tik su *sparse*. Tai
        teisėta būklė — paieška veiks kaip E2, tik be parafrazių.
        """
        model = embed.embedder()
        if model is None:
            return {}
        keys: list[str] = []
        texts: list[str] = []
        for doc in docs:
            for ord_, section in enumerate(kb._sections(doc)):
                keys.append(f"{doc['source']}#{ord_}")
                # Indeksuojam TĄ PATĮ tekstą, kurį agentas pasakys: pavadinimas, antraštė, raktai
                # ir nuvalytas turinys. Kitaip vektorius rodytų į ne tą, ką klientas išgirs.
                texts.append(
                    f"{doc['title']}. {section[0]}. {' '.join(doc['keywords'])}. "
                    f"{kb._speakable(section[1])[:700]}"
                )
        try:
            return dict(zip(keys, model.encode_passages(texts), strict=True))
        except Exception as exc:
            logger.warning(f"[KB] dense vectors skipped ({exc}) — index stays sparse-only")
            return {}

    def _points(self, docs) -> list[Any]:
        from qdrant_client import models

        vectors = self._dense(docs)
        points = []
        for doc in docs:
            for chunk in chunks(doc, vectors):
                vector: dict[str, Any] = {
                    SPARSE_VECTOR: models.SparseVector(
                        indices=list(chunk["sparse"].indices), values=list(chunk["sparse"].values)
                    ),
                    BODY_VECTOR: models.SparseVector(
                        indices=list(chunk["body"].indices), values=list(chunk["body"].values)
                    ),
                }
                if chunk["dense"] is not None:
                    vector[DENSE_VECTOR] = chunk["dense"]
                points.append(
                    models.PointStruct(id=chunk["id"], payload=chunk["payload"], vector=vector)
                )
        return points

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


def _level(lexical: float, floor: float) -> int:
    """2 = tvirtas atsakymas, 1 = pažymėtas spėjimas, 0 = nieko.

    Patikimumą sprendžia VIENA kalibruota skalė — leksinė, ta pati kaip failuose. Semantinė pusė
    rikiuoja, bet patikimumo neliečia, ir tai išmatuota, ne atsargumas:
    teisingų radinių kosinusas 0,780–0,929, klaidingų — 0,000–0,916; ne mūsų srities klausimai
    („automobilio remontas" 0,847) guli toje pačioje zonoje. Persidengia beveik visiškai, tad
    kosinusas negali būti kokybės vartai. Ir patikrinta, kad nieko neprarandam: su semantine riba
    0,84, 0,90 ar visai be jos rezultatas tas pats — hit@1 54 %, hit@2 62 %, tyla 1.

    Iš to seka ir pigesnė užklausa: `dense` vektorių iš Qdrant grąžinti nebereikia (žr. `retrieve`).
    """
    if lexical >= floor:
        return 2
    if lexical >= kb.HINT:
        return 1
    return 0


def _mentions(point: Any, wanted: tuple[str, ...]) -> bool:
    """Ar ši dalis apie prašytą įrenginį — tas pats sprendimas, kaip `knowledge_base._mentions`:
    tik kontroliuojamas tagas arba skyriaus antraštė, ne raktai ir ne tekstas."""
    payload = point.payload or {}
    declared = kb._fold(" ".join((*(payload.get("tags") or ()), str(payload.get("section") or ""))))
    return any(word in declared for word in wanted)


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

        lexical = for_query(query)
        if not lexical.indices:
            return []
        where = _filter(filter_metadata or {})
        prefer = tuple(kb._fold(word) for word in (filter_metadata or {}).get("prefer") or ())
        floor = kb.FLOOR if threshold is None else threshold
        sparse_query = models.SparseVector(
            indices=list(lexical.indices), values=list(lexical.values)
        )
        # Modelio gali nebūti, jis gali nesulaukti arba indeksas gali būti be `dense` — visais
        # atvejais paieška vyksta tik leksine puse. Tai E2 elgesys, ne avarija.
        dense_query = self._dense_query(query)
        wanted = max(top_k or 2, 2)

        if dense_query is None:
            found = self.qdrant.query_points(
                self.collection,
                query=sparse_query,
                using=SPARSE_VECTOR,
                query_filter=where,
                score_threshold=kb.HINT,
                limit=wanted * 5,
                with_payload=True,
                with_vectors=[BODY_VECTOR],
            ).points
            scored = [(point, point.score, point.score) for point in found]
        else:
            # Hibridas: plati atranka iš abiejų pusių, sujungimas rangais (RRF) serverio pusėje.
            # Rangais, ne balais: leksinis balas yra 0..1 skalėje, kosinusas — savo, ir juos sudėti
            # reikštų sudėti skirtingus dalykus (išmatuota: balų suma nepasitvirtino, RAG_SPRENDIMAI 2.2).
            found = self.qdrant.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(
                        query=sparse_query, using=SPARSE_VECTOR, filter=where, limit=PREFETCH
                    ),
                    models.Prefetch(
                        query=dense_query, using=DENSE_VECTOR, filter=where, limit=PREFETCH
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=where,
                limit=wanted * 5,
                with_payload=True,
                # Grąžinam TIK *sparse* vektorių: iš jo suskaičiuojam tikslų leksinį balą (RRF balas
                # yra rangų suma ir nieko nesako apie tai, ar atsakymas tvirtas). `dense` vektorių
                # neprašom — jie atsakyme sudarytų ~90 % svorio, o patikimumui nedaro nieko.
                with_vectors=[SPARSE_VECTOR, BODY_VECTOR],
            ).points
            scored = [(point, self._lexical_score(point, lexical), point.score) for point in found]

        # Trys lygiai. Tvirta, jei bent viena pusė tvirta: leksinė gaudo modelius ir klaidų kodus,
        # semantinė — parafrazes. Ribos abiem pusėms — išmatuotos, ne parinktos.
        # Tvarka: pirma lygis, tada saugyklos rangas (RRF arba leksinis balas), tada šaltinis —
        # kad lygūs balai abiejose realizacijose išsidėstytų vienodai.
        levels = [
            (
                point,
                lex,
                fused,
                _level(lex, floor),
                self._body_score(point, lexical),
                _mentions(point, prefer) if prefer else None,
            )
            for point, lex, fused in scored
        ]
        levels = [row for row in levels if row[3] > 0]
        # Lygius balus skiria: prašytas įrenginys, tada skyriaus atitikimas, tada šaltinis — ta pati
        # tvarka, kaip failų realizacijoje, kad dvi saugyklos atsakytų vienodai.
        levels.sort(
            key=lambda row: (-row[3], not row[5], -row[2], -row[4], row[0].payload["source"])
        )
        sure = [row for row in levels if row[3] == 2]
        chosen = sure[: top_k or 2] if sure else levels[:1]
        return [
            {
                "document": point.payload["text"],
                "score": round(lex, 3),
                "id": str(point.id),
                "metadata": {
                    "source": point.payload["source"],
                    "section": point.payload["section"],
                    "kind": point.payload["kind"],
                    "tags": point.payload["tags"],
                    "equipment": point.payload["equipment"],
                    "sure": level == 2,
                    "specific": specific,
                    "lexical": round(lex, 3),
                    # Saugyklos rangavimo balas: hibride tai RRF, leksiniame kelyje — tas pats
                    # leksinis balas. Metrikoms ir derinimui (E4), ne sprendimams.
                    "fused": round(fused, 4),
                },
            }
            for point, lex, fused, level, _body, specific in chosen
        ]

    def _dense_query(self, query: str) -> list[float] | None:
        """Semantinis užklausos vektorius arba None.

        None — teisėta būklė: modelio nėra, jis nesulaukė arba servisas nukrito. Bet kuriuo atveju
        paieška vyksta leksine puse (E2 elgesys). Išimtis čia NEGALI prasiveržti: skambutis nesibaigia
        dėl to, kad neatsakė modelis.
        """
        model = embed.embedder()
        if model is None:
            return None
        try:
            return model.encode_query(query)
        except Exception as exc:
            logger.warning(f"[KB] query embedding unavailable ({exc}) — searching lexically")
            return None

    def _body_score(self, point: Any, lexical) -> float:
        """Kiek sutampa pati dalis, be dokumento paviršiaus — lygių balų skirtukas."""
        return self._dot(point, BODY_VECTOR, lexical)

    def _lexical_score(self, point: Any, lexical) -> float:
        """Tikslus leksinis balas iš grąžinto *sparse* vektoriaus — ta pati 0..1 skalė kaip failuose."""
        return self._dot(point, SPARSE_VECTOR, lexical)

    @staticmethod
    def _dot(point: Any, name: str, lexical) -> float:
        stored = (point.vector or {}).get(name) if isinstance(point.vector, dict) else None
        if stored is None:
            return 0.0
        return Sparse(tuple(stored.indices), tuple(stored.values)).dot(lexical)

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
