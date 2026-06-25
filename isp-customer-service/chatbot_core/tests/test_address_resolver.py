"""
Tests for the resolve_address rich-result lookup (crm_mcp/tools/address_resolver.py).

Covers the §8.2 contract (kliento_identifikacijos_dizainas.md): every mismatch
class over the seeded §8.1 edge addresses, the street-name token matching for
compound names, and the agent tool wrapper.

Run: pytest tests/test_address_resolver.py -v
"""

import pytest


@pytest.fixture
def resolver(db_connection):
    """resolve_address bound to the seeded test DB."""
    from crm_mcp.tools.address_resolver import resolve_address

    def _run(**kwargs):
        return resolve_address(db_connection, kwargs)

    return _run


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


class TestCityResolution:
    def test_city_ok(self, resolver):
        r = resolver(city="Šiauliai")
        assert r["resolution"]["city"]["status"] == "ok"
        assert r["resolution"]["city"]["matched"] == "Šiauliai"

    def test_village_genitive_form(self, resolver):
        """'Bubių kaimas' (genitive + 'kaimas') resolves to Bubiai."""
        r = resolver(city="Bubių kaimas", street="Aušros", house_number="8")
        assert r["success"] is True
        assert r["customer_id"] == "CUST110"

    def test_district_plus_village_in_one_phrase(self, resolver):
        """'Šiaulių rajonas, Bubių kaimas' as ONE city string -> Bubiai."""
        r = resolver(city="Šiaulių rajonas, Bubių kaimas", street="Aušros", house_number="8")
        assert r["success"] is True
        assert r["customer_id"] == "CUST110"

    def test_district_reference_lists_villages(self, resolver):
        """'Šiaulių rajonas' is a district -> ask which village."""
        r = resolver(city="Šiaulių rajonas")
        assert r["resolution"]["city"]["status"] == "ambiguous"
        villages = {c["city"] for c in r["resolution"]["city"]["candidates"]}
        assert {"Ginkūnai", "Bubiai", "Vinkšnėnai"} <= villages

    def test_unknown_city(self, resolver):
        r = resolver(city="Klaipėda", street="Dainų")
        assert r["resolution"]["city"]["status"] == "not_found"
        assert r["success"] is False

    def test_unserved_city_recovered_by_street_and_house(self, resolver):
        """STT mishears the city ('Vilnius') but street+house pin Tilžės 60-7."""
        r = resolver(city="Vilnius", street="Tilžės", house_number="60", apartment_number="7")
        assert r["resolution"]["city"]["status"] == "recovered"
        assert r["resolution"]["city"]["matched"] == "Šiauliai"
        assert r["success"] is True
        assert r["customer_id"] == "CUST105"

    def test_unserved_city_not_recovered_when_house_wrong(self, resolver):
        """Wrong street from STT must NOT snap to a real address: Žeimių 60
        does not exist (Žeimių has house 12), so recovery refuses."""
        r = resolver(city="Vilnius", street="Žeimių", house_number="60")
        assert r["resolution"]["city"]["status"] == "not_found"
        assert r["success"] is False

    def test_unserved_city_not_recovered_without_house(self, resolver):
        """Street alone never auto-recovers the city — the agent must ask."""
        r = resolver(city="Vilnius", street="Tilžės")
        assert r["resolution"]["city"]["status"] == "not_found"
        assert r["success"] is False


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


class TestApartmentAndContracts:
    def test_flats_house_requires_apartment(self, resolver):
        """Dainų g. 5 has several flats -> ask the apartment number."""
        r = resolver(city="Šiauliai", street="Dainų", house_number="5")
        apt = r["resolution"]["apartment"]
        assert apt["status"] == "required"
        assert apt["contracts_count"] >= 2
        assert "buto" in r["hint"]

    def test_flat_resolves_unique_customer(self, resolver):
        r = resolver(city="Šiauliai", street="Dainų", house_number="5", apartment_number="5")
        assert r["success"] is True
        assert r["customer_id"] == "CUST102"

    def test_wrong_apartment(self, resolver):
        r = resolver(city="Šiauliai", street="Dainų", house_number="5", apartment_number="99")
        assert r["resolution"]["apartment"]["status"] == "not_found"
        assert r["success"] is False

    def test_house_without_flats_two_contracts_asks_surname(self, resolver):
        """Dainų g. 7: two contracts, no flats -> surname disambiguation."""
        r = resolver(city="Šiauliai", street="Dainų", house_number="7")
        assert r["resolution"]["apartment"]["status"] == "required"
        assert "pavard" in r["hint"].lower()

    def test_surname_disambiguates(self, resolver):
        r = resolver(city="Šiauliai", street="Dainų", house_number="7", surname="Petraitis")
        assert r["success"] is True
        assert r["customer_id"] == "CUST107"
        assert r["resolution"]["surname_matched"] is True

    def test_surname_mismatch_no_pii_leak(self, resolver):
        r = resolver(city="Šiauliai", street="Dainų", house_number="7", surname="Jonaitis")
        assert r["success"] is False
        assert r["resolution"]["surname_matched"] is False
        # The hint must not reveal the registered surnames.
        assert "Petraitis" not in r["hint"]
        assert "Kazlauskas" not in r["hint"]


class TestFullRecoveryPath:
    def test_zeimiu_full_address_in_ginkunai(self, resolver):
        r = resolver(city="Ginkūnai", street="Žeimių", house_number="12", apartment_number="6")
        assert r["success"] is True
        assert r["customer_id"] == "CUST109"


class TestAgentToolWrapper:
    def test_tool_attaches_profile_on_success(self, db_connection):
        from agent.tools import resolve_address as tool

        r = tool(city="Bubiai", street="Aušros", house_number="8")
        assert r["success"] is True
        profile = r["customer"]
        assert profile["customer_id"] == "CUST110"
        assert profile["addresses"][0]["full_address"].startswith("Šiaulių r.")

    def test_tool_passes_hint_through(self, db_connection):
        from agent.tools import resolve_address as tool

        r = tool(city="Šiauliai", street="Žeimių")
        assert r["success"] is False
        assert "Ginkūnai" in r["hint"]

    def test_find_customer_by_account_code(self, db_connection):
        from agent.tools import find_customer

        r = find_customer(account_code="AB-10109")
        assert r["success"] is True
        assert r["customer_id"] == "CUST109"

    def test_find_customer_unknown_account_code(self, db_connection):
        from agent.tools import find_customer

        r = find_customer(account_code="AB-99999")
        assert r["success"] is False
