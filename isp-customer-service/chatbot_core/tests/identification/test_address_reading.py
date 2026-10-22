"""Adreso supratimas — what the caller's words say: city, street, house, flat (agent/perceive/nlu.py).

The reader is deterministic and registry-validated: no LLM, no invented streets. Each row is one
way a caller says an address; the reader must return exactly the parts given (a part left out
of the row is not checked). Known gaps are listed as such and fail the run once fixed.
"""

import pytest
from agent.perceive.nlu import AddressReading

from .helpers import extract, read

FUNCTION = "Adreso supratimas"


def gap(text, expect, label, why):
    return pytest.param(text, expect, id=label, marks=pytest.mark.xfail(strict=True, reason=why))


READINGS = [
    # --- the usual forms -----------------------------------------------------------------
    pytest.param(
        "Tilžės gatvė 60, butas 7",
        {"street": "Tilžės g.", "house": "60", "apartment": "7"},
        id="gatvė, namas, butas skaičiais",
    ),
    pytest.param(
        "Šiauliai, Tilžės gatvė 60, butas 3",
        {"city": "Šiauliai", "street": "Tilžės g.", "house": "60", "apartment": "3"},
        id="su miestu",
    ),
    pytest.param(
        "Tilžės 60 butas 7",
        {"street": "Tilžės g.", "house": "60", "apartment": "7"},
        id="be žodžio gatvė",
    ),
    pytest.param(
        "Tilžės gatvėje 60",
        {"street": "Tilžės g.", "house": "60", "apartment": None},
        id="gatvė vietininku",
    ),
    pytest.param(
        "Gyvenu Tilžės gatvėj, namas šešiasdešimt",
        {"street": "Tilžės g.", "house": "60"},
        id="šnekamoji forma, namas žodžiu",
    ),
    pytest.param(
        "Vilniaus 29",
        {"street": "Vilniaus g.", "house": "29", "apartment": None},
        id="tik gatvė ir namas",
    ),
    pytest.param(
        "Vilniaus gatvė 33 butas 2",
        {"street": "Vilniaus g.", "house": "33", "apartment": "2"},
        id="dviženkliai skaičiai nesulimpa",
    ),
    # --- numbers in words --------------------------------------------------------------
    pytest.param(
        "Tilžės gatvė šešiasdešimt butas septintas",
        {"street": "Tilžės g.", "house": "60", "apartment": "7"},
        id="skaičiai žodžiais",
    ),
    pytest.param(
        "Tilžės keturiasdešimt keturi",
        {"street": "Tilžės g.", "house": "44", "apartment": None},
        id="dešimtys ir vienetai žodžiais",
    ),
    pytest.param(
        "Tilžės 60 butas trys",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        id="butas kiekiniu skaitvardžiu",
    ),
    pytest.param(
        "Tildžės 6 0 būtų namas, o butas 3", {"house": "60", "apartment": "3"}, id="šeši nulis = 60"
    ),
    # --- ASR forms ------------------------------------------------------------------------
    pytest.param(
        "Tilžės 60 buto 3",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        id="buto vietoj butas",
    ),
    pytest.param(
        "Tilžės 60 būto 3",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        id="būto (ASR)",
    ),
    pytest.param(
        "Šiauliai Dainų 5 butas 5",
        {"city": "Šiauliai", "street": "Dainų g.", "house": "5", "apartment": "5"},
        id="miestas be kablelių",
    ),
    pytest.param(
        "Tilžės 60 būtos 3",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        id="būtos (ASR ilgoji ū)",
    ),
    pytest.param(
        "Dainu 5 butas 5", {"street": "Dainų g.", "house": "5", "apartment": "5"}, id="be nosinės"
    ),
    pytest.param(
        "Ne. Tai but... but namo numeris yra 60",
        {"house": "60", "apartment": None},
        id="nukirptas but ir namo numeris",
    ),
    pytest.param(
        "Tilžės 60 būtų namas, o butas 3",
        {"house": "60", "apartment": "3"},
        id="skaičius prieš namas yra namas",
    ),
    # --- house letters, compound streets, villages ----------------------------------------
    pytest.param("Sodo gatvė 122F", {"street": "Sodo g.", "house": "122F"}, id="namas su raide"),
    pytest.param(
        "Girėno Dariaus 25",
        {"street": "S. Dariaus ir S. Girėno g.", "house": "25"},
        id="sudėtinė gatvė kita tvarka",
    ),
    pytest.param(
        "Dariaus ir Girėno gatvė 25 butas 45",
        {"street": "S. Dariaus ir S. Girėno g.", "house": "25", "apartment": "45"},
        id="sudėtinė gatvė be inicialų",
    ),
    pytest.param(
        "Ginkūnai, Žeimių 12, butas 6",
        {"city": "Ginkūnai", "street": "Žeimių g.", "house": "12", "apartment": "6"},
        id="kaimas, gatvė, namas, butas",
    ),
    pytest.param(
        "Šiaulių rajonas, Ginkūnai, Žeimių gatvė 12",
        {"city": "Ginkūnai", "street": "Žeimių g.", "house": "12"},
        id="rajonas ir kaimas",
    ),
    pytest.param(
        "Vilniaus gatvė 60",
        {"street": "Vilniaus g.", "house": "60", "city": None},
        id="Vilniaus gatvė nėra Vilniaus miestas",
    ),
    # --- flat-only answers (to „koks butas?") ---------------------------------------------
    pytest.param("butas trys", {"house": None, "apartment": "3"}, id="tik butas: butas trys"),
    pytest.param("butas 3", {"house": None, "apartment": "3"}, id="tik butas: butas 3"),
    pytest.param("butas trečias", {"house": None, "apartment": "3"}, id="tik butas: butas trečias"),
    # --- known gaps -------------------------------------------------------------------------
    gap(
        "Trečias butas",
        {"house": None, "apartment": "3"},
        "tik butas: trečias butas",
        "skaičius PRIEŠ „butas“ skaitomas kaip namas",
    ),
    gap(
        "3 butas",
        {"house": None, "apartment": "3"},
        "tik butas: 3 butas",
        "skaičius PRIEŠ „butas“ skaitomas kaip namas",
    ),
    gap(
        "Tilžės 60 trečias butas",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        "butas po namo: trečias butas",
        "skaičius PRIEŠ „butas“ pametamas",
    ),
    gap(
        "trečias butas, Tilžės 60",
        {"street": "Tilžės g.", "house": "60", "apartment": "3"},
        "butas prieš gatvę",
        "namas ir butas sukeičiami",
    ),
    gap(
        "Tilžės 60-7",
        {"street": "Tilžės g.", "house": "60", "apartment": "7"},
        "namas-butas per brūkšnį",
        "butas po brūkšnio pametamas",
    ),
    gap(
        "Vilniaus g. 33-2",
        {"street": "Vilniaus g.", "house": "33", "apartment": "2"},
        "užrašyta forma g. 33-2",
        "butas po brūkšnio pametamas",
    ),
    gap(
        "Žemaitės keturiolika, antras butas",
        {"street": "Žemaitės g.", "house": "14", "apartment": "2"},
        "keturiolika, antras butas",
        "„keturiolika antras“ suklijuojama į 16, butas pametamas",
    ),
    gap(
        "Tilzes 60",
        {"street": "Tilžės g.", "house": "60"},
        "gatvė be lietuviškų raidžių",
        "be diakritikų gatvė neatpažįstama",
    ),
    gap(
        "Bubių kaime, Aušros 8",
        {"city": "Bubiai", "street": "Aušros g.", "house": "8"},
        "kaimas vietininku",
        "„Bubių kaime“ neskaitomas kaip Bubiai",
    ),
]


@pytest.mark.parametrize(("text", "expect"), READINGS)
def test_the_address_is_read(db_connection, text, expect):
    """Adresas perskaitomas"""
    r = read(text)
    got = {k: getattr(r, k) for k in expect}
    assert got == expect


NOTHING = [
    pytest.param("neveikia internetas", id="problema, ne adresas"),
    pytest.param("taip, tvirtinu", id="patvirtinimas"),
    pytest.param("", id="tuščias tekstas"),
]


@pytest.mark.parametrize("text", NOTHING)
def test_no_address_is_invented(text):
    """Adreso neišgalvoja"""
    r = extract(text)
    assert r.street is None and r.house is None and r.apartment is None


def test_an_empty_text_is_an_empty_reading():
    """Tuščias tekstas — tuščias skaitymas"""
    assert extract("") == AddressReading()


def test_the_seed_registry_is_the_one_read(db_connection):
    """Registras iš DB"""
    from agent.tooling import LocalToolProvider

    registry = LocalToolProvider().address_registry()
    assert "Tilžės g." in registry.streets and "Tilžės" in registry.street_names
    assert "Šiauliai" in registry.localities


def test_a_confident_street_scores_high():
    """Aiški gatvė — aukštas pasitikėjimas"""
    assert extract("Tilžės gatvė šešiasdešimt butas septintas").street_confidence >= 0.9


# --- from test_wave10_quick.py ---


class TestV7AddressReading:
    STREETS = ["Aušros g.", "Tilžės g.", "Vilniaus g."]

    @pytest.mark.parametrize(
        ("said", "street"),
        [
            ("Vakar vakare, po audros", None),  # eval I1: became „Aušros gatvė"
            ("Ausros 5", "Aušros g."),  # a number makes the near match an address
            ("Aušros gatvė", "Aušros g."),  # an exact name
            ("Tilžės 60 butas 3", "Tilžės g."),
        ],
    )
    def test_a_near_street_needs_address_evidence(self, said, street):
        from agent.perceive.nlu import extract_address

        assert extract_address(said, self.STREETS, ["Šiauliai"]).street == street
