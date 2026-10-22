"""Gatvės paieška — the spoken street found in the registry (crm_mcp/tools/address_resolver.py).

Token-set matching for spoken names, the street with or without a city, the street found in
another locality, and what the agent's resolve_address tool passes on.
"""

import pytest

FUNCTION = "Gatvės paieška"


# Each row: what the caller said → the customer found, or the street status.
STREETS = [
    pytest.param(
        {"street": "Tilžės g.", "house_number": "60", "apartment_number": "7"},
        "CUST105",
        id="registro forma",
    ),
    pytest.param(
        {"street": "Tilžės gatvė", "house_number": "60", "apartment_number": "3"},
        "CUST101",
        id="su žodžiu gatvė",
    ),
    pytest.param(
        {"city": "Šiauliai", "street": "Tilžės", "house_number": "60", "apartment_number": "7"},
        "CUST105",
        id="su miestu",
    ),
    pytest.param(
        {"street": "Tilžės", "house_number": "60", "apartment_number": "7"},
        "CUST105",
        id="be miesto",
    ),
    pytest.param({"street": "Dainavo", "house_number": "4"}, "CUST302", id="sutrumpinta galūnė"),
    pytest.param(
        {"street": "Tilvyko", "house_number": "8"}, "CUST301", id="panaši gatvė (Tilvyčio)"
    ),
    pytest.param({"street": "Vilties", "house_number": "15"}, "CUST303", id="Vilties ne Vilniaus"),
    pytest.param(
        {"street": "Girėno Dariaus", "house_number": "25", "apartment_number": "45"},
        "CUST104",
        id="sudėtinė gatvė kita tvarka",
    ),
    pytest.param(
        {"street": "Žeimių", "house_number": "12", "apartment_number": "6"},
        "CUST109",
        id="kaimo gatvė be kaimo",
    ),
    pytest.param(
        {"street": "Kosmonautų alėja", "house_number": "7"}, "not_found", id="tokios gatvės nėra"
    ),
    pytest.param(
        {"street": "Tilzes", "house_number": "60", "apartment_number": "7"},
        "CUST105",
        id="be lietuviškų raidžių",
        marks=pytest.mark.xfail(strict=True, reason="be diakritikų gatvė nerandama"),
    ),
]


@pytest.mark.parametrize(("said", "found"), STREETS)
def test_the_street_is_found(resolver, said, found):
    """Gatvė randama"""
    r = resolver(**said)
    if found == "not_found":
        assert r["success"] is False and r["resolution"]["street"]["status"] == "not_found"
    else:
        assert r["success"] is True and r["customer_id"] == found


# --- from test_address_resolver.py ---


class TestStreetMatching:
    """Token-set matching for spoken street names."""

    def _score(self, query, candidate):
        from crm_mcp.tools.address_resolver import street_match_score

        return street_match_score(query, candidate)

    def test_exact(self):
        assert self._score("Dainų g.", "Dainų g.") == 1.0

    def test_suffix_variants(self):
        assert self._score("Dainų gatvė", "Dainų g.") == 1.0
        assert self._score("Dainu", "Dainų g.") > 0.7  # missing diacritics

    def test_compound_word_order(self):
        """'Girėno Dariaus' (swapped, no initials) -> full compound name."""
        assert self._score("Girėno Dariaus", "S. Dariaus ir S. Girėno g.") == 1.0
        assert self._score("Dariaus ir Girėno", "S. Dariaus ir S. Girėno g.") == 1.0

    def test_compound_partial(self):
        score = self._score("Dariaus", "S. Dariaus ir S. Girėno g.")
        assert 0.4 < score < 1.0  # partial -> candidate, not silent accept

    def test_different_streets_stay_apart(self):
        assert self._score("Tilžės", "Dainų g.") < 0.5


class TestStreetResolution:
    def test_street_not_in_city_found_elsewhere(self, resolver):
        """The Žeimių recovery: said Šiauliai, street lives in Ginkūnai."""
        r = resolver(city="Šiauliai", street="Žeimių")
        street = r["resolution"]["street"]
        assert street["status"] == "not_in_city"
        elsewhere = street["found_elsewhere"]
        assert any(e["city"] == "Ginkūnai" and e["district"] == "Šiaulių r." for e in elsewhere)
        assert "Ginkūnai" in r["hint"]

    def test_partial_input_street_ok(self, resolver):
        """Early verification: city+street only -> street ok, asks for house."""
        r = resolver(city="Šiauliai", street="Dainų")
        assert r["resolution"]["street"]["status"] == "ok"
        assert r["resolution"]["house"]["status"] == "not_given"
        assert r["success"] is False

    def test_compound_street_resolves(self, resolver):
        r = resolver(
            city="Šiauliai", street="Girėno Dariaus", house_number="25", apartment_number="45"
        )
        assert r["success"] is True
        assert r["customer_id"] == "CUST104"


class TestStreetFirstResolution:
    """No city given — derive the locality from the street (street-first)."""

    def test_street_only_derives_city(self, resolver):
        r = resolver(street="Tilžės")
        assert r["resolution"]["city"]["status"] == "derived"
        assert r["resolution"]["city"]["matched"] == "Šiauliai"

    def test_full_address_without_city_resolves(self, resolver):
        r = resolver(street="Tilžės", house_number="60", apartment_number="7")
        assert r["success"] is True
        assert r["customer_id"] == "CUST105"

    def test_village_street_derives_district_locality(self, resolver):
        """'Žeimių' (no city) -> Ginkūnai (the only locality with that street)."""
        r = resolver(street="Žeimių", house_number="12", apartment_number="6")
        assert r["success"] is True
        assert r["customer_id"] == "CUST109"

    def test_no_city_no_street_asks_for_street(self, resolver):
        r = resolver()
        assert r["resolution"]["street"]["status"] == "not_given"
        assert "gatv" in r["hint"].lower()

    def test_unknown_street_without_city(self, resolver):
        r = resolver(street="Nesamų")
        assert r["resolution"]["street"]["status"] == "not_found"
        assert r["success"] is False


def test_tool_attaches_profile_on_success(db_connection):
    from agent.tools import resolve_address as tool

    r = tool(city="Bubiai", street="Aušros", house_number="8")
    assert r["success"] is True
    profile = r["customer"]
    assert profile["customer_id"] == "CUST110"
    assert profile["addresses"][0]["full_address"].startswith("Šiaulių r.")


def test_tool_passes_hint_through(db_connection):
    from agent.tools import resolve_address as tool

    r = tool(city="Šiauliai", street="Žeimių")
    assert r["success"] is False
    assert "Ginkūnai" in r["hint"]
