"""Agento ribos: apie ką jam leista ieškoti žinių, o apie ką ne (RAG planas, E3b).

Andrius (2026-09-24): *„agentas turi žinoti savo ribas ir neišeiti iš jų. Ieškoma informacija, kuri
padėtų spręsti gedimą."*

Riba turi DVI AŠIS, ir vienos nepakanka:

    TEMA       ar apie mūsų paslaugą / įrangą, kuri ją teikia?
    PASKIRTIS  ar apie tai, kad mūsų paslauga VEIKTŲ (diagnozė, prijungimas, nustatymas)?

„Kurį routerį rekomenduotumėt pirkti" temą turi, o paskirties ne — ir būtent dėl to yra antra ašis.

Šis testas yra ATSISAKYMŲ rinkinys: jis tikrina ne tai, ką agentas randa, o tai, ko jis NEIEŠKO. Be
jo „agentas žino savo ribas" yra nuomonė.
"""

from __future__ import annotations

import pytest
from agent import knowledge_base as kb
from agent import knowledge_need as need

# Klausimai MŪSŲ srityje: privalo pasiekti žinių bazę.
OURS = [
    "kaip telefone patikrinti ar prisijungęs prie wifi",
    "kokios lemputės dega ant routerio",
    "kaip sukonfigūruoti wan į dhcp",
    "į kurį lizdą jungti lan kabelį",
    "android telefone nerodo wifi tinklo",
    "telefone neveikia internetas",
    "ar geriau perkrauti routerį ar palaukti",
    # Pirkimo žodis be pasirinkimo formos yra gedimo klausimas, ne rekomendacijos prašymas.
    "nusipirkau naują dėžutę parduotuvėje, ar ji veiks",
    "pasiėmiau routerį iš draugo, ar toks veiks",
]

# Nukrypimai: žinių bazės neturi pasiekti VISAI.
NOT_OURS = [
    ("koks šiandien oras Šiauliuose", "topic"),
    ("ar galite padėti su automobilio remontu", "topic"),
    ("kokia šiandien euro ir dolerio kursas", "topic"),
    ("ar turite laisvų darbo vietų", "topic"),
    ("kurį routerį rekomenduotumėt pirkti", "purpose"),
    ("ką siūlote naujam namui", "purpose"),
    ("kokį televizorių verta įsigyti", "purpose"),
    ("ar galit rekomenduoti gerą wifi kartotuvą", "purpose"),
    ("windows nepasileidžia", "device"),
    ("kodėl telefonas kaista", "device"),
    ("", "empty"),
]


@pytest.mark.parametrize("heard", OURS)
def test_our_own_questions_reach_the_knowledge_base(heard):
    got = need.from_caller(heard)
    assert isinstance(got, need.Need), f"atmesta be reikalo: {heard}"


@pytest.mark.parametrize("heard, why", NOT_OURS)
def test_questions_outside_our_boundary_are_refused(heard, why):
    got = need.from_caller(heard)
    assert isinstance(got, need.Refusal), f"praleista be reikalo: {heard}"
    assert got.why == why


def test_the_whole_sentence_is_searched_not_the_filtered_words():
    """Vartai sprendžia TIK ar ieškoti; ieškoma visu sakiniu.

    Atfiltruotas poreikis sugriautų patikimumą: balas normuojamas pagal tai, ko klausta, tad palikus
    vien „wifi", klausimas „ar wifi kenkia sveikatai" gautų balą 1,000 ir taptų tvirtu atsakymu.
    """
    heard = "ar wifi kenkia sveikatai"
    got = need.from_caller(heard)
    assert got.words == heard
    assert got.trace["kept"] == "wifi"  # žurnale matyti, KODĖL praleista
    assert kb.find(got.words, limit=1)[0].score < 0.9


def test_the_named_device_is_recognised_as_a_word_not_a_substring():
    """„ios" yra „kokios" viduje: pirmoji versija kiekvieną „kokios lemputės" laikė iPhone klausimu."""
    assert need.named_device("android telefone nerodo wifi") == "android"
    assert need.named_device("iphone nemato tinklo") == "iphone"
    assert need.named_device("samsung telefone nėra wifi") == "android"
    assert need.named_device("kokios lemputės dega ant routerio") is None
    assert need.named_device("kokia problema") is None


def test_the_boundary_is_the_knowledge_not_the_code():
    """Temos riba yra tai, apie ką kalba dokumentai — tad nauja žinia ją išplečia be kodo.

    Ir atvirkščiai: kliento žodis, kurio nėra nė vieno dokumento raktuose, yra TURINIO spraga.
    Būtent taip buvo atmesta „televizorius rodo juodą ekraną" — dokumentas yra, o žodžio „televizorius"
    raktuose nebuvo.
    """
    assert need.ours("routeris") and need.ours("lemputės") and need.ours("televizorius")
    assert need.ours("wan") and need.ours("lan"), "trumpi techniniai žodžiai turi būti matomi"
    assert not need.ours("automobilio") and not need.ours("oras")


def test_a_card_declared_need_passes_without_gates():
    """Technikas pats yra riba: kortelės deklaruotas poreikis netikrinamas."""
    got = need.from_card("tplink lights meaning", equipment="tplink")
    assert got.asked_by == "card"
    assert got.words == "tplink lights meaning"
    assert got.equipment == "tplink"


def test_every_boundary_word_list_exists_in_the_locale():
    """Riba yra DUOMENYS: sąrašai gyvena žodyne, ne kode, ir jų negali nebūti."""
    for name in (
        "knowledge_out_of_purpose",
        "knowledge_choice_form",
        "knowledge_device_trouble",
        "knowledge_service_words",
        "device_android",
        "device_iphone",
        "device_windows",
        "device_macos",
    ):
        assert need._vocab(name), f"žodyne nėra '{name}'"


# --- kortelės paprašytos gilesnės žinios --------------------------------------------------


def _state_with_need(need_text: str | None):
    from types import SimpleNamespace

    return SimpleNamespace(
        turn=SimpleNamespace(
            plan={"rule": "case.check_lights", "say": {"knowledge_need": need_text}}
        ),
        case=SimpleNamespace(fault="link_down_local"),
        diagnosis=SimpleNamespace(verdicts={}),
    )


def test_the_step_gets_the_knowledge_its_card_asked_for():
    """Kortelė sprendžia gedimą, o žinia ją PAPILDO: klientas paklaus „kuri iš tų lempučių?"."""
    from agent.speak.context_card import _step_knowledge

    lines = _step_knowledge(_state_with_need("routerio lemputes indikatoriai"), None)
    assert lines and "DEEPER KNOWLEDGE" in lines[0]
    # Atsarga, ne scenarijus: agentas to neskaito savo iniciatyva.
    assert "use ONLY if the caller asks" in lines[0]
    assert "lempu" in lines[0].lower() or "indikator" in lines[0].lower()


def test_a_step_without_a_declared_need_gets_nothing():
    from agent.speak.context_card import _step_knowledge

    assert _step_knowledge(_state_with_need(None), None) == []


def test_every_declared_need_finds_something():
    """Poreikis, kurio niekas neatsako, yra pažadas be turinio — tai tikrina ir startas."""
    from agent.contract import cards as catalog

    declared = [
        (name, step.knowledge_need)
        for name, card in catalog.cards().items()
        for solution in card.solution
        for step in solution.steps
        if step.knowledge_need
    ]
    assert declared, "bent viena kortelė turi deklaruoti gilesnių žinių poreikį"
    for name, need_text in declared:
        assert kb.find(need_text, limit=1), f"{name}: '{need_text}' nieko neranda"
