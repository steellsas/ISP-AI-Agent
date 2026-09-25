"""Žinių indeksas Qdrant'e (RAG planas, E2).

Testai eina per Qdrant kliento VIETINĮ režimą (`:memory:`), tad CI tikrina tą patį kelią be serverio
ir be konteinerio. Ko vietinis režimas neparodo — payload indeksai iš tikrųjų sukuriami, aliaso
perjungimas gyvame serveryje, skaitymo raktas negali rašyti — tikrinta rankomis prieš tikrą serverį
ir surašyta `docs/review/RAG_PLANAS.md` 9 skyriuje.

Svarbiausias šio failo testas yra pirmasis: *sparse* sandauga LYGI leksiniam balui. Iš to seka, kad
Qdrant negali atsakyti kitaip nei failai — o jei atsako, klaida yra indekse, ne „modelyje" (jo dar
nėra).
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from adapters.retrieval import KnowledgeIndex, LexicalRetriever, QdrantRetriever, sparse
from adapters.retrieval import questions as recall
from adapters.retrieval.qdrant_store import chunks, content_hash, families
from agent import knowledge_base as kb
from ports.retrieval import RetrieverPort

QUESTION = "kaip sukonfigūruoti routerį po gamyklinio atstatymo"


@contextmanager
def no_embeddings():
    """Blokas be semantinės pusės — taip tikrinama E2 sutartis (tik leksinė paieška)."""
    import os

    from adapters.retrieval import embed

    previous = os.environ.get("EMBED")
    os.environ["EMBED"] = "off"
    embed.use(None)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EMBED", None)
        else:
            os.environ["EMBED"] = previous
        embed.use(None)


@pytest.fixture(scope="module")
def index():
    """Indeksas BE `dense` vektorių: E2 būklė, kurią turi atkartoti ir failai."""
    from qdrant_client import QdrantClient

    with no_embeddings():
        built = KnowledgeIndex(QdrantClient(":memory:"))
        built.rebuild()
    return built


@pytest.fixture(scope="module")
def search(index):
    return QdrantRetriever(index.qdrant, index.alias)


# --- ar Qdrant gali atsakyti kitaip nei failai --------------------------------------------


def test_the_sparse_dot_product_is_the_lexical_score():
    """Dokumento vektorius × užklausos vektorius = `_keyword_score`, iki slankiojo kablelio.

    Tai ir yra E2 pagrindas: leksinė logika lieka mūsų kode (lietuviškos šaknys, galūnės, IDF), o
    Qdrant tik suskaičiuoja sandaugą. Todėl saugyklos pakeitimas negali pakeisti atsakymų.
    """
    query = sparse.for_query(QUESTION)
    worst = 0.0
    for doc in kb.documents():
        for section in kb._sections(doc):
            through_vector = sparse.for_chunk(doc, section).dot(query)
            through_files = kb._keyword_score(QUESTION, doc, section)
            worst = max(worst, abs(through_vector - through_files))
    assert worst < 1e-9, f"didžiausias neatitikimas {worst:.2e}"


def test_the_same_recall_through_qdrant_as_through_files(search):
    """Tos pačios ribos, tas pats rinkinys — indeksas privalo būti ne blogesnis už failus."""
    with no_embeddings():
        ok, seen = recall.passes(search)
        _, files = recall.passes(LexicalRetriever())
    assert ok, str(seen)
    # Abi realizacijos atsako vienodai; leidžiam vieno klausimo skirtumą, nes Qdrant *sparse*
    # svorius laiko float32, tad tikslią balų lygybę (pasitaiko) suskaido kitaip.
    assert abs(seen.hit2 - files.hit2) <= 1.5 / seen.total
    assert abs(seen.hit1 - files.hit1) <= 1.5 / seen.total


def test_almost_every_question_gets_the_same_documents(search):
    files = LexicalRetriever()

    def sources(retriever, question):
        seen: list[str] = []
        for chunk in retriever.retrieve(question, top_k=2):
            if chunk["metadata"]["source"] not in seen:
                seen.append(chunk["metadata"]["source"])
        return seen

    asked = recall.questions()
    with no_embeddings():
        same = sum(sources(search, q) == sources(files, q) for q, _ in asked)
    assert same >= 0.9 * len(asked), f"vienodai tik {same}/{len(asked)}"


def test_the_port_is_satisfied(search):
    assert isinstance(search, RetrieverPort)


# --- trys atsakymo lygiai ----------------------------------------------------------------


def test_three_levels_behave_as_in_the_files(search):
    strong = search.retrieve(QUESTION, top_k=2)
    assert strong and all(chunk["metadata"]["sure"] for chunk in strong)

    weak = search.retrieve("ar galite man padėti su automobilio remontu", top_k=2)
    assert len(weak) <= 1
    assert all(not chunk["metadata"]["sure"] for chunk in weak)

    assert search.retrieve("kokia bus rytoj oro temperatūra Šiauliuose", top_k=2) == []


def test_the_text_in_the_index_is_already_speakable(search):
    """Nuvalymas atliekamas INDEKSUOJANT, tad į atsakymą markdown nepatenka niekada."""
    for chunk in search.retrieve("ką reiškia oranžinė lemputė ant routerio", top_k=2):
        for marker in ("**", "|", "`", "---"):
            assert marker not in chunk["document"]


# --- filtras ------------------------------------------------------------------------------


def test_the_filter_pushes_down_to_the_index(search):
    only_equipment = search.retrieve(
        "ką reiškia lemputė", top_k=3, filter_metadata={"kind": "equipment"}
    )
    assert only_equipment and {c["metadata"]["kind"] for c in only_equipment} == {"equipment"}


@pytest.mark.parametrize("asked", ["tv", "internet", "internet_down"])
def test_the_problem_filter_keeps_neutral_knowledge(search, asked):
    """Ta pati semantika, kaip `_matches`: šeima arba tiksli problema, o neutralūs praeina visada."""
    for chunk in search.retrieve("neveikia", top_k=10, filter_metadata={"problem": asked}):
        document = next(d for d in kb.documents() if d["source"] == chunk["metadata"]["source"])
        assert not document["problem"] or kb._same_problem(asked, document["problem"])
    # Meistro kaina turi būti pasiekiama interneto gedimo viduryje.
    found = search.retrieve(
        "kiek kainuoja techniko vizitas", top_k=3, filter_metadata={"problem": "internet"}
    )
    assert "procedures/technician_visit.md" in {c["metadata"]["source"] for c in found}


def test_the_problem_family_is_computed_at_ingestion():
    assert families(("internet_down", "internet_slow")) == ["internet"]
    assert families(("tv",)) == ["tv"]
    assert families(()) == []


# --- versijos, atnaujinimas, skirtumai ---------------------------------------------------


def test_the_version_is_the_collection_behind_the_alias(index):
    assert index.current() == f"{index.alias}_v{index.version()}"
    assert index.version() >= 1


def test_the_index_matches_the_files(index):
    assert index.drift() == {}
    assert index.indexed() == {doc["source"]: content_hash(doc) for doc in kb.documents()}
    expected = sum(len(kb._sections(doc)) for doc in kb.documents())
    assert index.qdrant.count(index.current()).count == expected


def test_one_document_is_reindexed_alone(index):
    """Kaina proporcinga PAKEITIMUI, ne bazei — ir be liekanų."""
    source = "troubleshooting/wifi_problems.md"
    before = index.qdrant.count(index.current()).count
    parts = index.upsert_document(source)
    assert parts == len(kb._sections(kb.document(source)))
    assert index.qdrant.count(index.current()).count == before
    assert index.drift() == {}


def test_a_shorter_document_leaves_no_stale_chunks(index, monkeypatch):
    """Dokumentas sutrumpėjo — pasenusios dalys turi išnykti, ne likti indekse."""
    source = "troubleshooting/wifi_problems.md"
    document = kb.document(source)
    full = len(kb._sections(document))
    shortened = dict(document, body="## Vienintelis skyrius\nTekstas.")
    monkeypatch.setattr(kb, "document", lambda s: shortened if s == source else document)
    index.upsert_document(source)
    assert len(index.indexed()) == len(kb.documents())
    left = index.qdrant.count(
        index.current(),
        count_filter=_source_filter(source),
    ).count
    assert left < full
    monkeypatch.undo()
    index.upsert_document(source)  # atstatom
    assert index.drift() == {}


def test_a_removed_document_leaves_nothing_behind(index):
    source = "faq/common_questions.md"
    index.remove_document(source)
    assert source not in index.indexed()
    assert index.drift()[source] == "added"  # failas yra, indekse nebėra
    index.upsert_document(source)
    assert index.drift() == {}


def test_drift_sees_a_changed_document(index, monkeypatch):
    doc = kb.document("troubleshooting/internet_slow.md")
    changed = tuple(
        dict(d, body=d["body"] + "\n## Naujas skyrius\nNauja žinia.") if d is doc else d
        for d in kb.documents()
    )
    monkeypatch.setattr(kb, "documents", lambda: changed)
    assert index.drift() == {"troubleshooting/internet_slow.md": "changed"}


def test_a_refusing_canary_leaves_the_alias_alone(index):
    """Blogas indeksas sustabdomas PRIEŠ aliaso perjungimą — gamyboje lieka veikiantis senas."""
    before = index.current()
    with pytest.raises(RuntimeError, match="canary refused"):
        index.rebuild(canary=lambda collection: False)
    assert index.current() == before
    assert not index.qdrant.collection_exists(f"{index.alias}_v{index.version() + 1}")


def test_a_rebuild_switches_the_alias_and_keeps_the_previous(index):
    before = index.current()
    with no_embeddings():  # E2 sutartis: aliasai ir kanarėlė nepriklauso nuo modelio
        ok, _ = recall.passes(QdrantRetriever(index.qdrant, before))
        assert ok
        index.rebuild(canary=lambda c: recall.passes(QdrantRetriever(index.qdrant, c))[0])
    assert index.current() != before
    assert index.qdrant.collection_exists(before), "senoji kolekcija reikalinga atstatymui"


def test_chunk_ids_are_stable_across_runs():
    """Tas pats dokumentas, indeksuotas du kartus, perrašo tuos pačius taškus."""
    document = kb.document("troubleshooting/wifi_problems.md")
    assert [c["id"] for c in chunks(document)] == [c["id"] for c in chunks(document)]


def _source_filter(source: str):
    from qdrant_client import models

    return models.Filter(
        must=[models.FieldCondition(key="source", match=models.MatchValue(value=source))]
    )


# --- atsarginis kelias: skambutis nesibaigia dėl indekso ----------------------------------


def test_a_broken_backend_falls_back_to_the_files():
    """Svarbiausia E2 savybė. Failai yra tiesos šaltinis, tad indekso netekimas yra nepatogumas,
    ne skambučio pabaiga."""

    class Dead:
        name = "dead"

        def retrieve(self, *a, **k):
            raise ConnectionError("qdrant is down")

    try:
        kb.use(Dead())
        found = kb.find(QUESTION, limit=2)
        assert found, "turėjo nusileisti į failus"
        assert found[0].source == "troubleshooting/internet_factory_reset_dhcp.md"
    finally:
        kb.use(None)


def test_the_backend_choice_comes_from_the_environment(monkeypatch):
    from adapters.retrieval import configure_from_env

    monkeypatch.delenv("KB_BACKEND", raising=False)
    assert configure_from_env() == "files"
    assert kb.backend() is None

    # Prašyta Qdrant, bet serverio nėra: agentas VIS TIEK turi žinias — tik per failus.
    monkeypatch.setenv("KB_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6399")
    monkeypatch.setenv("QDRANT_TIMEOUT", "0.3")
    assert configure_from_env() == "files"
    assert kb.backend() is None
    assert kb.find(QUESTION, limit=1)


def test_the_agent_sees_the_same_passages_through_either_backend(index):
    """`find()` yra vienintelės durys: kortelės ir `context_card` apie saugyklą nežino."""
    through_files = kb.find(QUESTION, limit=2)
    try:
        kb.use(QdrantRetriever(index.qdrant, index.alias))
        through_qdrant = kb.find(QUESTION, limit=2)
    finally:
        kb.use(None)
    assert [p.source for p in through_qdrant] == [p.source for p in through_files]
    assert all(p.sure for p in through_qdrant)
    assert all(p.text and p.kind and p.source for p in through_qdrant)


# --- E3: hibridas ir jo nusileidimai ------------------------------------------------------


@pytest.fixture(scope="module")
def hybrid():
    """Indeksas SU `dense` vektoriais. Modelis kraunamas kartą visam moduliui."""
    from adapters.retrieval import embed
    from qdrant_client import QdrantClient

    model = embed.embedder()
    if model is None:
        pytest.skip("embedding'ai išjungti (EMBED=off)")
    # Pakaitinam SINCHRONIŠKAI: kitaip pirmosios užklausos nesulauktų modelio ir testai matuotų
    # nusileidimą, o ne hibridą (gamyboje tai daroma fone, žr. `_warm_embeddings`).
    model.warm()
    built = KnowledgeIndex(QdrantClient(":memory:"))
    built.rebuild()
    return built


def test_the_index_holds_both_sides(hybrid):
    """Viena kolekcija, du vektoriai: leksinis ir semantinis."""
    from adapters.retrieval.qdrant_store import DENSE_VECTOR, SPARSE_VECTOR

    records, _ = hybrid.qdrant.scroll(hybrid.current(), limit=5, with_vectors=True)
    assert records
    for record in records:
        assert SPARSE_VECTOR in record.vector
        assert len(record.vector[DENSE_VECTOR]) == 384
        assert record.payload["model"]


def test_the_hybrid_is_not_worse_than_sparse_alone(hybrid):
    """Hibridas turi pridėti, ne atimti — kitaip modelio nereikia."""
    from adapters.retrieval import embed

    search = QdrantRetriever(hybrid.qdrant, hybrid.alias)
    with_model = recall.measure(search)
    try:
        embed.use(None)  # ta pati kolekcija, tik be semantinės pusės
        import os

        os.environ["EMBED"] = "off"
        sparse_only = recall.measure(search)
    finally:
        os.environ.pop("EMBED", None)
        embed.use(None)
    assert with_model.hit2 >= sparse_only.hit2
    assert with_model.silent <= sparse_only.silent


def test_both_scores_are_reported(hybrid):
    """Atsakymas pasako ir kalibruotą leksinį balą, ir saugyklos rangavimo balą (metrikoms)."""
    for chunk in QdrantRetriever(hybrid.qdrant, hybrid.alias).retrieve(QUESTION, top_k=2):
        assert 0.0 <= chunk["metadata"]["lexical"] <= 1.0
        assert chunk["metadata"]["fused"] > 0


def test_only_the_lexical_side_decides_confidence(hybrid):
    """Išmatuota: kosinusas teisingų ir klaidingų radinių beveik nesiskiria (0,78–0,93 prieš
    0,00–0,92), o ne mūsų srities klausimai guli toje pačioje zonoje — „automobilio remontas" 0,847.
    Todėl semantinė pusė rikiuoja, bet patikimumo nesprendžia. Patikrinta, kad nieko neprarandam:
    su semantine riba ir be jos rezultatas tas pats."""
    from adapters.retrieval import qdrant_store as store

    assert store._level(0.10, kb.FLOOR) == 1
    assert store._level(0.90, kb.FLOOR) == 2
    assert store._level(0.01, kb.FLOOR) == 0


def test_a_dead_embedding_service_does_not_break_the_search(hybrid, monkeypatch):
    """Svarbiausia E3 savybė: balsas negali laukti modelio.

    Modelis nutyla — paieška vyksta leksine puse, kaip E2. Skambutis nenutrūksta ir atsakymas
    nesugenda; tik parafrazių pagalba laikinai išnyksta.
    """
    from adapters.retrieval import embed

    class Dead:
        name = "dead"

        def encode_query(self, text):
            raise ConnectionError("embedding service is down")

        def encode_passages(self, texts):
            raise ConnectionError("embedding service is down")

    search = QdrantRetriever(hybrid.qdrant, hybrid.alias)
    monkeypatch.setattr(embed, "_shared", Dead())
    found = search.retrieve(QUESTION, top_k=2)
    assert found, "turėjo atsakyti vien leksine puse"
    assert found[0]["metadata"]["source"] == "troubleshooting/internet_factory_reset_dhcp.md"
    assert found[0]["metadata"]["lexical"] > 0


def test_a_slow_model_is_not_waited_for(monkeypatch):
    """`EMBED_TIMEOUT` yra riba LAUKIMUI: nesulaukę grąžinam None ir einam sparse puse."""
    import time as clock

    from adapters.retrieval import embed

    slow = embed.Local()
    monkeypatch.setattr(embed, "TIMEOUT", 0.05)
    monkeypatch.setattr(
        slow, "_loaded", lambda: type("M", (), {"encode": lambda *a, **k: clock.sleep(5)})()
    )
    started = clock.perf_counter()
    assert slow.encode_query("kodėl neveikia internetas") is None
    assert clock.perf_counter() - started < 1.0, "laukė ilgiau, nei leista"


# --- E4: eksploatacija — saugiklis, versijos, sveikata ------------------------------------


def test_a_model_mismatch_turns_the_semantic_half_off(own_index, monkeypatch):
    """Kito modelio vektoriai gyvena kitoje erdvėje — juos lyginant rikiavimas taptų atsitiktinis.

    TYLIAI. Todėl nesutapus semantinės pusės nebenaudojam: paieška veikia leksine puse, žurnale lieka
    įrašas, o atsakymas vis tiek yra. Tai ir yra blue/green keitimo saugiklis.
    """
    from adapters.retrieval import embed
    from adapters.retrieval.health import counters

    hybrid = own_index
    search = QdrantRetriever(hybrid.qdrant, hybrid.alias)
    assert search.index_model() == embed.MODEL, "indeksas pastatytas tuo pačiu modeliu"
    assert search._dense_query("lemputės") is not None

    before = counters.snapshot()["model_mismatch"]
    monkeypatch.setattr(embed, "MODEL", "kitas/modelis")
    fresh = QdrantRetriever(hybrid.qdrant, hybrid.alias)  # naujas worker'is gamyboje
    assert fresh._dense_query("lemputės") is None
    assert counters.snapshot()["model_mismatch"] > before
    # Ir svarbiausia: atsakymas vis tiek yra.
    assert fresh.retrieve(QUESTION, top_k=1)


def test_the_index_says_which_model_built_it(own_index):
    from adapters.retrieval import embed

    assert own_index.model() == embed.MODEL


@pytest.fixture
def own_index():
    """Savas indeksas testams, kurie KEIČIA versijas: bendro `hybrid` jie sugadintų kitiems."""
    from adapters.retrieval import embed
    from qdrant_client import QdrantClient

    if embed.embedder() is None:
        pytest.skip("embedding'ai išjungti (EMBED=off)")
    embed.embedder().warm()
    built = KnowledgeIndex(QdrantClient(":memory:"))
    built.rebuild()
    return built


def test_the_alias_can_be_pointed_and_rolled_back(own_index):
    """Blue/green: perkūrimas palieka senąją kolekciją, tad atstatymas yra viena operacija."""
    before = own_index.current()
    own_index.rebuild(canary=lambda c: recall.passes(QdrantRetriever(own_index.qdrant, c))[0])
    after = own_index.current()
    assert after != before
    assert len(own_index.collections()) >= 2

    back = own_index.rollback()
    assert back == before and own_index.current() == before
    own_index.point_alias(after)
    assert own_index.current() == after


def test_old_versions_are_pruned_but_the_rollback_target_stays(own_index):
    """Be valymo kolekcijos kaupiasi — per dieną jų buvo septynios, kiekviena su savo vektoriais."""
    while len(own_index.collections()) < 3:
        own_index.rebuild()
    current = own_index.current()
    removed = own_index.prune(keep=2)
    left = own_index.collections()
    assert current in left and len(left) == 2
    assert removed and current not in removed


def test_health_reports_the_four_questions(own_index):
    """Eksploatacijai reikia atsakymų į keturis klausimus vienu kvietimu."""
    from adapters.retrieval import health
    from agent import knowledge_base as kb

    hybrid = own_index
    # Skaitliukai vieni visam procesui: ankstesnių testų nusileidimai čia teisėtai keltų aliarmą.
    health.counters.reset()
    try:
        kb.use(QdrantRetriever(hybrid.qdrant, hybrid.alias))
        seen = health.check(qdrant=hybrid.qdrant)
    finally:
        kb.use(None)
    assert seen.backend == "qdrant"
    assert seen.collection == hybrid.current() and seen.points > 0
    assert seen.index_model and seen.drift == {}
    assert seen.recall is not None
    assert seen.ok, seen.alarms


def test_health_raises_an_alarm_when_the_index_drifts(own_index, monkeypatch):
    from adapters.retrieval import health
    from agent import knowledge_base as kb

    hybrid = own_index
    health.counters.reset()
    changed = tuple(
        dict(d, body=d["body"] + "\n## Naujas skyrius\nNauja žinia.") if i == 0 else d
        for i, d in enumerate(kb.documents())
    )
    monkeypatch.setattr(kb, "documents", lambda: changed)
    try:
        kb.use(QdrantRetriever(hybrid.qdrant, hybrid.alias))
        seen = health.check(qdrant=hybrid.qdrant)
    finally:
        kb.use(None)
    assert not seen.ok
    assert any("skiriasi nuo failų" in alarm for alarm in seen.alarms)


def test_the_counters_see_what_the_search_did(hybrid):
    from adapters.retrieval.health import counters

    before = counters.snapshot()
    QdrantRetriever(hybrid.qdrant, hybrid.alias).retrieve(QUESTION, top_k=2)
    after = counters.snapshot()
    assert after["searches"] == before["searches"] + 1
    assert after["p95_ms"] >= 0.0
