"""Žinių bazė kaip agento žinios (4b banga, radiniai AJ ir AK).

Andrius (2026-09-23): „įrangos informacija ir algoritmai kaip galima konfiguruoti ar patarimai
gali būti skirtingais tag kad agentas surastų tiksliai to ko reikia."

Todėl tikrinam ne „ar kažką grąžina", o ar grąžina TĄ, ko reikia: rūšį, įrangą ir dokumentą.
"""

import pytest
from agent import knowledge_base as kb


def _sources(passages):
    return {p.source for p in passages}


class TestEveryDocumentDeclaresWhatItIs:
    def test_all_have_a_kind_and_tags(self):
        for doc in kb.documents():
            assert doc["kind"] in kb.KINDS, doc["source"]
            assert doc["tags"], f"{doc['source']}: no tags — nothing will find it"
            assert doc["title"], doc["source"]

    def test_the_kinds_are_the_ones_the_engine_asks_for(self):
        kinds = {doc["kind"] for doc in kb.documents()}
        # equipment = what a device IS; howto = how to configure it; procedure = our own
        # rules; troubleshooting = a fault road; faq = short answers.
        assert {"equipment", "howto", "procedure", "faq", "troubleshooting"} >= kinds


class TestTheQuestionFindsItsDocument:
    """One table: the caller's own words -> the document that must answer them."""

    @pytest.mark.parametrize(
        "question, expected",
        [
            ("kaip pakeisti wifi slaptažodį", "faq/common_questions.md"),
            (
                "kaip sukonfigūruoti routerį po gamyklinio atstatymo",
                "troubleshooting/internet_factory_reset_dhcp.md",
            ),
            ("kada atvyks meistras ir kiek kainuos", "procedures/technician_visit.md"),
            ("televizorius nerodo kanalų", "troubleshooting/tv_no_signal.md"),
            ("kaip prisijungti prie wifi telefone", "troubleshooting/wifi_problems.md"),
            ("internetas labai lėtas vakarais", "troubleshooting/internet_slow.md"),
        ],
    )
    def test_it_is_found(self, question, expected):
        assert expected in _sources(kb.find(question, limit=3)), question

    def test_a_question_about_nothing_we_know_finds_nothing(self):
        """The honest "not my area" must stay possible — silence is better than a wrong doc."""
        assert kb.find("kokia bus rytoj oro temperatūra Šiauliuose") == []


class TestTheKindIsTheFilter:
    def test_asking_for_an_algorithm_gets_an_algorithm(self):
        found = kb.find("kaip sukonfigūruoti wan nustatymus", kind="howto")
        assert found and {p.kind for p in found} == {"howto"}

    def test_asking_about_the_device_gets_the_device(self):
        found = kb.find("kur yra reset mygtukas", kind="equipment")
        assert found and {p.kind for p in found} == {"equipment"}


class TestTheCallersOwnEquipment:
    def test_a_tplink_document_does_not_answer_for_another_box(self):
        """A caller with a Huawei box must not hear TP-Link's button layout."""
        question = "kur ant routerio yra reset mygtukas"
        mine = _sources(kb.find(question, kind="equipment", equipment="tplink"))
        other = _sources(kb.find(question, kind="equipment", equipment="router"))
        assert "equipment/router_tplink.md" in mine
        assert "equipment/router_tplink.md" not in other

    def test_a_document_with_no_equipment_tag_answers_for_everyone(self):
        found = _sources(kb.find("ką reiškia routerio lemputės", equipment="router"))
        assert "faq/common_questions.md" in found


class TestWhatIsReturned:
    def test_a_passage_carries_its_source(self):
        """Atsakymas visada turi adresą: dokumentą IR skyrių, kad būtų patikrinamas."""
        found = kb.find("kaip pakeisti wifi slaptažodį", limit=1)
        assert found and found[0].cite.endswith(f"({found[0].source})")
        assert found[0].source.endswith(".md") and found[0].title
        assert found[0].text and len(found[0].text) <= 700

    def test_a_section_not_the_whole_file(self):
        """Klientas išgirsta ATSAKYMĄ, ne instrukciją.

        Anksčiau čia buvo tikrinamas FAQ atsakymas. Nuo E4a (klausiamieji žodžiai nebesveria) tas
        pats klausimas grąžina TP-Link žingsnius — `192.168.0.1 → Wireless Security` — t. y. tai, ką
        klientas gali padaryti. Todėl tikrinam tikslą: viena dalis, ir ji VEIKSMINGA.
        """
        found = kb.find("kaip pakeisti wifi slaptažodį", limit=1)
        assert len(found) == 1 and len(found[0].text) < 700
        actionable = f"{found[0].title} {found[0].text}".lower()
        assert "slaptaž" in actionable or "192.168" in actionable
