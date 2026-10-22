"""Buto paieška — the flat: asked only when the house has flats (T-9b), never filled in from
the DB (no address probing), not asked for a private house (T-4).
"""

import pytest

from .helpers import _agent

FUNCTION = "Buto paieška"


# Each row: street + house (+ flat) → the customer, or the flat status the agent must act on.
FLATS = [
    pytest.param(
        {"street": "Tilžės", "house_number": "60"},
        "required",
        id="T-9b daugiabutis be buto — klausti",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "60", "apartment_number": "3"},
        "CUST101",
        id="daugiabutis su butu 3",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "60", "apartment_number": "7"},
        "CUST105",
        id="daugiabutis su butu 7",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "60", "apartment_number": "9"},
        "not_found",
        id="tokio buto nėra",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "12"},
        "required",
        id="vienas butas name — vis tiek klausti",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "16"}, "CUST005", id="T-4 namas be butų — neklausti"
    ),
    pytest.param({"street": "Vilties", "house_number": "17"}, "required", id="du butai — klausti"),
    pytest.param(
        {"street": "Vilties", "house_number": "17", "apartment_number": "5"},
        "CUST307",
        id="du butai, butas 5",
    ),
]


@pytest.mark.parametrize(("said", "expect"), FLATS)
def test_the_flat_is_asked_only_when_needed(resolver, said, expect):
    """Butas klausiamas tik kai reikia"""
    r = resolver(**said)
    if expect in ("required", "not_found"):
        assert r["success"] is False and r["resolution"]["apartment"]["status"] == expect
        assert "buto" in r["hint"].lower()
    else:
        assert r["success"] is True and r["customer_id"] == expect


# After „Koks buto numeris?" the caller often says only the number.
FLAT_ANSWERS = [
    pytest.param("butas 7", id="butas 7"),
    pytest.param("butas trys", id="butas žodžiu"),
    pytest.param(
        "7",
        id="tik skaičius",
        marks=pytest.mark.xfail(strict=True, reason="skaičius po buto klausimo užrašomas į namą"),
    ),
    pytest.param(
        "trys",
        id="tik skaičius žodžiu",
        marks=pytest.mark.xfail(strict=True, reason="skaičius po buto klausimo užrašomas į namą"),
    ),
    pytest.param(
        "Trečias",
        id="kelintinis",
        marks=pytest.mark.xfail(strict=True, reason="skaičius po buto klausimo užrašomas į namą"),
    ),
]


@pytest.mark.parametrize("answer", FLAT_ANSWERS)
def test_the_answer_to_the_flat_question_is_the_flat(db_connection, answer):
    """Atsakymas į buto klausimą — butas"""
    from agent.perceive.slots import prefill_slots_from_text

    a = _agent()
    a.state.intake.problem_type = "internet_down"
    prefill_slots_from_text(a.state, a.runtime, "Tilžės 60")
    a.state.messages.append({"role": "assistant", "content": "Koks jūsų buto numeris?"})
    prefill_slots_from_text(a.state, a.runtime, answer)
    p = a.state.identity.profile
    assert p.house.value == "60" and p.apartment.value in ("3", "7")


# --- from test_identification_rules.py ---


class TestApartmentByRegistry:
    """№1: buto klausiama TIK kai name >1 sutartis (resolverio mechanika)."""

    def test_single_contract_resolves_without_apartment(self, db_connection):
        import json

        from agent.tools import execute_tool

        r = json.loads(
            execute_tool(
                "resolve_address",
                {"street": "Vilniaus g.", "house_number": "29", "city": "Šiauliai"},
            )
        )
        assert r["success"] is True and r["customer_id"] == "CUST009"

    def test_multi_contract_requires_apartment(self, db_connection):
        import json

        from agent.tools import execute_tool

        r = json.loads(
            execute_tool(
                "resolve_address",
                {"street": "Tilžės g.", "house_number": "60", "city": "Šiauliai"},
            )
        )
        assert r["success"] is False
        assert r["resolution"]["apartment"]["status"] == "required"
        assert "buto" in (r.get("hint") or "")


# --- from test_address_resolver.py ---


def test_flats_house_requires_apartment(resolver):
    """Dainų g. 5 has several flats -> ask the apartment number."""
    r = resolver(city="Šiauliai", street="Dainų", house_number="5")
    apt = r["resolution"]["apartment"]
    assert apt["status"] == "required"
    assert apt["contracts_count"] >= 2
    assert "buto" in r["hint"]


def test_flat_resolves_unique_customer(resolver):
    r = resolver(city="Šiauliai", street="Dainų", house_number="5", apartment_number="5")
    assert r["success"] is True
    assert r["customer_id"] == "CUST102"


def test_single_flat_still_requires_the_caller_to_say_it(resolver):
    """Žeimių g. 12 has ONE contract, in a flat. It must NOT resolve on
    street+house: filling the apartment in from the DB would reveal a part the
    caller never said (address probing). Ask for it instead."""
    r = resolver(city="Ginkūnai", street="Žeimių", house_number="12")
    assert r["success"] is False
    assert r["customer_id"] is None
    assert r["resolution"]["apartment"]["status"] == "required"
    assert "buto" in r["hint"]
    assert "12-6" not in r["hint"]  # the flat number is not leaked


def test_single_flat_resolves_once_the_caller_says_it(resolver):
    r = resolver(city="Ginkūnai", street="Žeimių", house_number="12", apartment_number="6")
    assert r["success"] is True
    assert r["customer_id"] == "CUST109"


def test_house_without_a_flat_resolves_as_is(resolver):
    """A private house has no apartment to reveal -> street+house is enough."""
    r = resolver(city="Bubiai", street="Aušros", house_number="8")
    assert r["success"] is True
    assert r["customer_id"] == "CUST110"


def test_wrong_apartment(resolver):
    r = resolver(city="Šiauliai", street="Dainų", house_number="5", apartment_number="99")
    assert r["resolution"]["apartment"]["status"] == "not_found"
    assert r["success"] is False
