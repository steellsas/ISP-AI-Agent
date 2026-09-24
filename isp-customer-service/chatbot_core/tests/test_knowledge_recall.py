"""Atgaminimas: ar paieška randa TĄ dokumentą, kurio klausė klientas (RAG planas, E1).

Kam atskiras testas: `test_knowledge_base.py` tikrina sutartį — kad dokumentas turi rūšį, kad
filtras veikia, kad žingsniai nuskaitomi. Bet paieškos KOKYBĖ yra skaičius, ir jį reikia matuoti,
o ne tikėti. Šis testas yra arbitras kiekvienam paieškos pakeitimui: be jo „pagerinom paiešką" yra
nuomonė.

Rinkinys — `knowledge_questions.yaml`, kliento žodžiais. Jis taip pat įgyvendina taisyklę, kad
kiekvienas naujas dokumentas atkeliauja su savo klausimais: `test_every_document_has_questions`.

Ribos (`MIN_HIT1`, `MIN_HIT2`) yra REGRESIJOS sargas, ne idealas. Jas kelia tas, kas pagerina
paiešką — ir tik pamatavęs.
"""

from pathlib import Path

import pytest
import yaml
from agent import knowledge_base as kb

QUESTIONS_FILE = Path(__file__).with_name("knowledge_questions.yaml")

# Kiek dokumentas privalo turėti klausimų. Vienas klausimas nieko nepasako: parafrazė gali
# atsitiktinai sutapti su tagu.
MIN_QUESTIONS_PER_DOCUMENT = 2

# Prieš E1: 46 % hit@1, 54 % hit@2, TYLA 6. Po E1 (IDF svoriai, lietuviškos galūnės, trys lygiai):
# 53 % / 56 %, tyla 1. Ribos su atsarga triukšmui — vienas klausimas iš 68 yra 1,5 p.p.
MIN_HIT1 = 0.50
MIN_HIT2 = 0.54

# Kiek klausimų gali likti visai be atsakymo. Vienas: „moku už šimtą, o gaunu dešimt" neturi nė
# vienos bendros šaknies su jokiu dokumentu — leksinė paieška to principiškai negali surasti.
# Būtent tokie klausimai ir yra išmatuotas argumentas už E3 (embedding'ai), o ne nuojauta.
MAX_SILENT = 1


def _load() -> list[tuple[str, tuple[str, ...]]]:
    """[(klausimas, priimtini dokumentai)] — `or:` išvardina sąžiningai tinkančius kitus."""
    raw = yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8")) or {}
    out: list[tuple[str, tuple[str, ...]]] = []
    for source, asks in raw.items():
        for ask in asks:
            if isinstance(ask, dict):
                out.append((str(ask["ask"]), (source, *(ask.get("or") or ()))))
            else:
                out.append((str(ask), (source,)))
    return out


QUESTIONS = _load()


def _found(question: str, limit: int = 2) -> list[str]:
    """Dokumentai, kuriuos paieška grąžina šiam klausimui — be filtrų, sunkiausiu atveju."""
    seen: list[str] = []
    for passage in kb.find(question, limit=limit):
        if passage.source not in seen:
            seen.append(passage.source)
    return seen


def test_the_question_set_is_big_enough():
    """Mažas rinkinys derina triukšmą: prie 18 klausimų vienas jų yra 5,6 p.p."""
    assert len(QUESTIONS) >= 60, f"tik {len(QUESTIONS)} klausimų"


def test_every_document_has_questions():
    """Nauja žinia be klausimų yra žinia, kurios niekas neras."""
    raw = yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8")) or {}
    documented = {doc["source"] for doc in kb.documents()}
    missing = sorted(documented - set(raw))
    assert missing == [], f"dokumentai be klausimų: {missing}"
    thin = sorted(s for s, asks in raw.items() if len(asks) < MIN_QUESTIONS_PER_DOCUMENT)
    assert thin == [], f"per mažai klausimų: {thin}"
    unknown = sorted(set(raw) - documented)
    assert unknown == [], f"klausimai apie nesamus dokumentus: {unknown}"


def test_every_question_is_answered_by_some_document():
    """Nė vienas klausimas negali likti be atsakymo VISAI — tyla yra blogiausias atsakymas.

    Būtent tai gyvai ir atsitiko: `floor` nutildė atsakymą, kuris buvo faile, o modelis tada
    improvizavo.
    """
    silent = [q for q, _ in QUESTIONS if not _found(q)]
    assert len(silent) <= MAX_SILENT, f"paieška grąžino NIEKO: {silent}"


def test_recall_does_not_regress():
    hit1 = hit2 = 0
    misses: list[str] = []
    for question, accepted in QUESTIONS:
        found = _found(question)
        if found[:1] and found[0] in accepted:
            hit1 += 1
        if set(found[:2]) & set(accepted):
            hit2 += 1
        else:
            misses.append(f"  {question}\n      norėjom {accepted[0]}, gavom {found or 'NIEKO'}")

    n = len(QUESTIONS)
    report = (
        f"hit@1 {hit1}/{n} ({hit1 / n:.0%}, riba {MIN_HIT1:.0%}) · "
        f"hit@2 {hit2}/{n} ({hit2 / n:.0%}, riba {MIN_HIT2:.0%})\n" + "\n".join(misses)
    )
    assert hit2 / n >= MIN_HIT2, report
    assert hit1 / n >= MIN_HIT1, report


@pytest.mark.parametrize(
    "question, source",
    [
        # Filtras yra pirmas sluoksnis: kai skambučio kontekstas žinomas, kandidatų mažiau.
        ("ką reiškia oranžinė lemputė", "equipment/router_tplink.md"),
        ("kaip sukonfigūruoti routerį", "troubleshooting/internet_factory_reset_dhcp.md"),
    ],
)
def test_the_filter_narrows_instead_of_ranking(question, source):
    """Su rūšimi paieška negali grąžinti kitos rūšies dokumento — ir be jos ranga nesikeičia."""
    kind = next(d["kind"] for d in kb.documents() if d["source"] == source)
    found = kb.find(question, kind=kind, limit=3)
    assert found, question
    assert {p.kind for p in found} == {kind}


def test_a_weak_hit_is_marked_instead_of_hidden():
    """Trys lygiai: tvirtas atsakymas, pažymėtas spėjimas, sąžiningas nieko.

    Tai ir yra „tylos nebėra": spėjimas grąžinamas, bet su `sure=False`, kad agentas galėtų
    pasakyti „nesu tikras" vietoj improvizacijos.
    """
    # Ne mūsų sritis: vienintelis pažįstamas žodis yra „kokia" — balas subyra, grąžinama nieko.
    assert kb.find("kokia bus rytoj oro temperatūra Šiauliuose") == []
    # Silpnas, bet ne tuščias sutapimas: vienas spėjimas, pažymėtas kaip nepatikimas.
    weak = kb.find("ar galite man padėti su automobilio remontu")
    assert len(weak) <= 1
    assert all(not p.sure for p in weak)
    # Tvirtas sutapimas: pažymėtas kaip patikimas.
    strong = kb.find("kaip sukonfigūruoti routerį po gamyklinio atstatymo")
    assert strong and strong[0].sure


def test_nothing_markdown_reaches_the_reply():
    """Į atsakymą keliauja KALBA, ne dokumento formatavimas.

    Iki E1 kontekste atsidurdavo `- **POWER žalia** - routeris veikia`, o lentelės pilnai
    prarasdavo ryšį tarp lemputės ir spalvos. Brūkšnys sakinio VIDURYJE („WiFi ON/OFF - fizinis
    mygtukas") lieka: jis skaitomas natūraliai, skirtingai nuo sąrašo brūkšnio eilutės pradžioje.
    """
    for document in kb.documents():
        for section in kb._sections(document):
            text = kb._speakable(section[1])
            for marker in ("**", "__", "|", "`", "#", "---"):
                assert marker not in text, f"{document['source']}: {marker!r} -> {text[:80]}"


def test_the_table_keeps_the_column_next_to_its_value():
    """Lemputės reikšmė be stulpelio antraštės yra beprasmė, todėl lentelė tampa sakiniais."""
    found = kb.find("ką reiškia oranžinė lemputė ant routerio", limit=1)
    assert found and found[0].source == "equipment/router_tplink.md"
    assert "INTERNET — " in found[0].text
    assert "Raudona/Oranžinė: Nėra ryšio su tiekėju" in found[0].text


def test_the_problem_filter_drops_other_faults_but_keeps_neutral_knowledge():
    """`problem` buvo antraštėse, bet filtras jo nenaudojo (E1 defektas)."""
    for passage in kb.find("nėra signalo, nėra kanalų", problem="tv", limit=5):
        document = next(d for d in kb.documents() if d["source"] == passage.source)
        assert not document["problem"] or "tv" in document["problem"], passage.source
    # Neutrali žinia (įrangos instrukcija, procedūra, FAQ) praleidžiama per bet kurį gedimą:
    # klientas gali klausti apie meistro kainą interneto gedimo viduryje.
    asked = kb.find("kiek kainuoja techniko vizitas", problem="internet_down", limit=3)
    assert "procedures/technician_visit.md" in {p.source for p in asked}
