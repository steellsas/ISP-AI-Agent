"""Namo paieška — the house on the street; a wrong number lists the known ones (T-4)."""

import pytest

FUNCTION = "Namo paieška"


HOUSES = [
    pytest.param({"street": "Vilniaus", "house_number": "29"}, "CUST009", None, id="namas yra"),
    pytest.param(
        {"street": "Sodo", "house_number": "122f", "city": "Vinkšnėnai"},
        "CUST111",
        None,
        id="raidė mažąja",
    ),
    pytest.param(
        {"street": "Vilniaus", "house_number": "39"},
        None,
        {"29", "31", "33"},
        id="T-4 namo nėra — išvardija esamus",
    ),
    pytest.param(
        {"street": "Dainų", "house_number": "99", "city": "Šiauliai"},
        None,
        {"5", "7"},
        id="namo nėra Dainų gatvėje",
    ),
]


@pytest.mark.parametrize(("said", "found", "known"), HOUSES)
def test_the_house_is_found_or_the_known_ones_listed(resolver, said, found, known):
    """Namas randamas arba išvardijami esami"""
    r = resolver(**said)
    if found:
        assert r["success"] is True and r["customer_id"] == found
    else:
        house = r["resolution"]["house"]
        assert house["status"] == "not_found" and known <= set(house["known_houses"])


# --- from test_address_resolver.py ---


class TestHouseResolution:
    def test_house_not_found_lists_known(self, resolver):
        r = resolver(city="Šiauliai", street="Dainų", house_number="99")
        house = r["resolution"]["house"]
        assert house["status"] == "not_found"
        assert "5" in house["known_houses"]

    def test_house_with_letter(self, resolver):
        """'122F' house number, case-insensitive."""
        r = resolver(city="Vinkšnėnai", street="Sodo", house_number="122f")
        assert r["success"] is True
        assert r["customer_id"] == "CUST111"
