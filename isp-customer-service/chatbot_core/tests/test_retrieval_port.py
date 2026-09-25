"""Paieškos portas: ar saugyklą tikrai galima pakeisti neužkabinus agento (RAG planas, E1).

Kam šis testas dabar, kai saugykla dar viena: E2 atneša Qdrant, ir tada norisi žinoti, kad siūlė
yra tikra, o ne deklaruota. Todėl čia tikrinam tris dalykus:

  1. `LexicalRetriever` atitinka `RetrieverPort` sutartį (ne tik „turi tuos metodus" — `Protocol`);
  2. per portą grąžinami TIE PATYS dokumentai, kaip per `find()` — siūlė nieko neprarado;
  3. filtras keliauja `filter_metadata` raktais, kurie E2 taps Qdrant payload indeksais.
"""

from adapters.retrieval import LexicalRetriever
from agent import knowledge_base as kb
from ports.retrieval import RetrieverPort

QUESTION = "kaip sukonfigūruoti routerį po gamyklinio atstatymo"


def test_the_lexical_backend_satisfies_the_port():
    assert isinstance(LexicalRetriever(), RetrieverPort)


def test_the_port_returns_what_the_search_returns():
    """Ta pati užklausa per portą ir tiesiai — tie patys dokumentai ta pačia tvarka."""
    direct = [p.source for p in kb.find(QUESTION, limit=2)]
    through_port = [c["metadata"]["source"] for c in LexicalRetriever().retrieve(QUESTION, top_k=2)]
    assert through_port == direct
    assert direct, "klausimas privalo ką nors rasti"


def test_every_chunk_carries_its_source_and_confidence():
    """Atsakymas be šaltinio nėra patikrinamas, o be `sure` — agentas nežino, ar spėja."""
    for chunk in LexicalRetriever().retrieve(QUESTION, top_k=2):
        assert chunk["document"] and chunk["id"]
        assert chunk["metadata"]["source"].endswith(".md")
        assert isinstance(chunk["metadata"]["sure"], bool)
        assert chunk["metadata"]["kind"] in kb.KINDS


def test_the_filter_travels_through_the_port():
    """`filter_metadata` raktai — tie patys, kurie E2 taps payload indeksais Qdrant'e."""
    found = LexicalRetriever().retrieve(
        "nėra signalo, nėra kanalų", top_k=5, filter_metadata={"problem": "tv"}
    )
    for chunk in found:
        document = next(d for d in kb.documents() if d["source"] == chunk["metadata"]["source"])
        assert not document["problem"] or "tv" in document["problem"]
    only_equipment = LexicalRetriever().retrieve(
        "ką reiškia lemputė", top_k=3, filter_metadata={"kind": "equipment"}
    )
    assert only_equipment and {c["metadata"]["kind"] for c in only_equipment} == {"equipment"}


def test_reloading_keeps_the_backend_usable():
    """Failai yra saugykla: „užkrovimas" yra kešo atmetimas, ir po jo paieška veikia."""
    backend = LexicalRetriever()
    assert backend.is_loaded()
    assert backend.load() is True
    assert backend.retrieve(QUESTION, top_k=1)


# --- kaip radinys patenka į atsakymą -----------------------------------------------------


def _fake_state(heard: str, fault: str | None = None):
    """Minimalus būvis, kurio užtenka `_kb_answer`: kas pasakyta, koks gedimas, kokia įranga."""
    from types import SimpleNamespace

    return SimpleNamespace(
        dialog=SimpleNamespace(last_heard=heard),
        case=SimpleNamespace(fault=fault),
        diagnosis=SimpleNamespace(verdicts={}),
        # Ėjimo supratimas: čia gyvena AGENTO pasirinktas dokumentas (E4).
        turn=SimpleNamespace(understanding={}),
    )


def test_a_confident_answer_goes_in_with_its_source():
    from agent.speak.context_card import _kb_answer

    said = _kb_answer(_fake_state("kaip sukonfigūruoti routerį po gamyklinio atstatymo"), None)
    assert "[howto:" in said
    assert "NOT SURE" not in said


def test_an_off_topic_question_never_reaches_the_knowledge_base():
    """Nuo E3b vartai stoja PRIEŠ paiešką: ne mūsų sritis žinių bazės nepasiekia (radinys E3b).

    Iki tol tas pats klausimas grąžindavo pažymėtą spėjimą — geriau už tylą, bet vis tiek klaidinga:
    apie autoremontą mes neturim ir negalim turėti nieko.
    """
    from agent.speak.context_card import _kb_answer

    assert _kb_answer(_fake_state("ar galite man padėti su automobilio remontu"), None) == ""
    assert _kb_answer(_fake_state("koks šiandien oras Šiauliuose"), None) == ""
    assert _kb_answer(_fake_state("kurį routerį rekomenduotumėt pirkti"), None) == ""
    assert _kb_answer(_fake_state("windows nepasileidžia"), None) == ""


def test_the_call_s_service_narrows_the_search_not_the_card_name():
    """`case.fault` yra kortelės vardas; filtrui paduodama kortelės PASLAUGA (E1 klaida)."""
    from agent.speak.context_card import _service_of

    assert _service_of(_fake_state("", "dhcp_silent")) == "internet"
    # Skolos ar tiketo kortelė (`service: any`) savo problemų šeimos neturi — filtro nėra.
    assert _service_of(_fake_state("", "billing_suspended")) is None
    assert _service_of(_fake_state("", None)) is None
