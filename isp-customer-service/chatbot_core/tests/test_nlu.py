"""
Tests for deterministic address extraction (agent/nlu.py, NLU Track A).

Locks down pokalbio_variklis.md §4: registry-validated street + normalized
numbers, no LLM, no hallucinated streets. The pure function is tested with a
hand-given registry; one integration test loads the real seed registry.

Run: pytest tests/test_nlu.py -v
"""

import pytest
from agent.nlu import AddressReading, extract_address

STREETS = [
    "Tilžės g.",
    "Dainų g.",
    "Dailės g.",
    "Žemaitės g.",
    "S. Dariaus ir S. Girėno g.",
    "Žeimių g.",
    "Aušros g.",
    "Sodo g.",
    "Vilniaus g.",
]
LOCALITIES = ["Šiauliai", "Ginkūnai", "Bubiai", "Vinkšnėnai"]


def _extract(text) -> AddressReading:
    return extract_address(text, STREETS, LOCALITIES)


class TestStreetAndNumbers:
    def test_full_address_with_apartment_words(self):
        r = _extract("Tilžės gatvė šešiasdešimt butas septintas")
        assert r.street == "Tilžės g."
        assert r.house == "60"
        assert r.apartment == "7"
        assert r.street_confidence >= 0.9

    def test_city_street_house_apartment_digits(self):
        r = _extract("Šiauliai Dainų 5 butas 5")
        assert r.city == "Šiauliai"
        assert r.street == "Dainų g."
        assert r.house == "5"
        assert r.apartment == "5"

    def test_apartment_marker_tolerates_long_vowel_stt(self):
        # STT often writes "būtos"/"būto" for "butas"; the accented ū must still match the
        # "but" marker, else the caller's flat is silently dropped (observed live bug).
        for marker in ("būtos", "būto", "buto"):
            r = _extract(f"Tilžės 60 {marker} 3")
            assert r.house == "60" and r.apartment == "3", marker

    def test_spoken_tens_units_become_house(self):
        r = _extract("Tilžės keturiasdešimt keturi")
        assert r.street == "Tilžės g."
        assert r.house == "44"
        assert r.apartment is None

    def test_house_number_with_letter(self):
        r = _extract("Sodo gatvė 122F")
        assert r.street == "Sodo g."
        assert r.house == "122F"

    def test_compound_street_any_order(self):
        r = _extract("Girėno Dariaus 25")
        assert r.street == "S. Dariaus ir S. Girėno g."
        assert r.house == "25"


class TestConservative:
    def test_no_street_no_false_match(self):
        r = _extract("neveikia internetas")
        assert r.street is None
        assert r.house is None
        assert r.apartment is None

    def test_confirmation_is_empty(self):
        r = _extract("taip, tvirtinu")
        assert r.street is None and r.house is None

    def test_empty_text(self):
        r = _extract("")
        assert r == AddressReading()

    def test_unserved_city_not_returned(self):
        # "Vilniaus g." is a registry STREET; the city Vilnius is not a locality.
        r = _extract("Vilniaus gatvė 60")
        assert r.street == "Vilniaus g."
        assert r.house == "60"
        assert r.city is None  # Vilnius is not served -> no locality match


class TestLoadRegistryIntegration:
    def test_extract_over_seed_registry(self, db_connection):
        from agent.nlu import load_registry
        from agent.tools import get_db

        streets, localities = load_registry(get_db())
        assert "Tilžės g." in streets
        assert "Šiauliai" in localities

        r = extract_address("Tilžės 60 butas 7", streets, localities)
        assert r.street == "Tilžės g."
        assert r.house == "60"
        assert r.apartment == "7"


class TestClassifyProblem:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("neveikia internetas", "internet_down"),
            ("nėra interneto man", "internet_down"),
            ("internetas labai lėtas", "internet_slow"),
            ("viskas stringa ir buferiuoja", "internet_slow"),
            ("neveikia televizija", "tv"),
            ("klausimas dėl sąskaitos", "billing"),
            ("noriu sumokėti", "billing"),
            ("labas, kaip sekasi", None),
        ],
    )
    def test_keyword_classification(self, text, expected):
        from agent.nlu import classify_problem

        assert classify_problem(text) == expected

    def test_slow_beats_down(self):
        """'lėtas internetas' is slow, not down (specific keyword first)."""
        from agent.nlu import classify_problem

        assert classify_problem("internetas lėtas") == "internet_slow"


class TestExtractSymptoms:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("lemputės nedega", {"lights": "nedega"}),
            ("routerio lemputės dega žaliai", {"lights": "dega"}),
            ("lemputė mirksi", {"lights": "mirksi"}),
            ("jungiuosi per wifi", {"connection": "wifi"}),
            ("prijungta laidu", {"connection": "laidinis"}),
            ("neveikia visuose įrenginiuose", {"devices": "visi"}),
            ("internetas dingsta kartais", {"frequency": "protarpiais"}),
            ("dar ir televizija neveikia", {"services": "tv"}),
            ("lamputės nedaga", {"lights": "nedega"}),  # STT misspelling (live)
            ("lemputės dagą", {"lights": "dega"}),  # STT misspelling (live)
            ("labas", {}),
        ],
    )
    def test_categorical_symptoms(self, text, expected):
        from agent.nlu import extract_symptoms

        assert extract_symptoms(text) == expected

    def test_negation_beats_positive(self):
        """'nedega' must win over the substring 'dega'."""
        from agent.nlu import extract_symptoms

        assert extract_symptoms("lemputės nedega")["lights"] == "nedega"

    def test_multiple_categories(self):
        from agent.nlu import extract_symptoms

        got = extract_symptoms("per wifi, lemputės nedega")
        assert got == {"connection": "wifi", "lights": "nedega"}


class TestPrefillWiring:
    def test_user_turn_prefills_slots(self, db_connection):
        """A caller turn populates the slots before the LLM, via the agent."""
        from unittest.mock import patch

        from agent.react_agent import ReactAgent
        from agent.slots import SlotStatus

        agent = ReactAgent(caller_phone="+37060012345")
        agent.state.turn_count = 1  # skip the greeting branch

        msg = type("M", (), {"content": "Gerai.", "tool_calls": None})()
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            agent.run_until_response("neveikia internetas Tilžės 60 butas 7")

        p = agent.state.profile
        assert p.street.value == "Tilžės g." and p.street.status == SlotStatus.HEARD
        assert p.house.value == "60"
        assert p.apartment.value == "7"
        # R1: the stated problem is captured as a durable fact.
        assert agent.state.problem_type == "internet_down"

    def test_symptoms_prefilled_and_surfaced(self, db_connection):
        """A symptom turn populates state.symptoms and the facts block (A3)."""
        from unittest.mock import patch

        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012345")
        agent.state.turn_count = 1

        msg = type("M", (), {"content": "Gerai.", "tool_calls": None})()
        with (
            patch("agent.react_agent.llm_tool_completion", return_value=msg),
            patch("agent.react_agent.get_last_call_stats", return_value={}),
        ):
            agent.run_until_response("internetas neveikia, lemputės nedega, jungiuosi per wifi")

        assert agent.state.symptoms["lights"] == "nedega"
        assert agent.state.symptoms["connection"] == "wifi"
        facts = agent._state_facts_block()
        assert "SYMPTOMAI" in facts and "lights=nedega" in facts
