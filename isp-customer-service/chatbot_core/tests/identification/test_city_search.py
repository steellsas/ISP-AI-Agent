"""Vietovės paieška — city, village, district, and a city we do not serve.

T-5 (Žeimių g. is in Ginkūnai), T-11 (Kaunas is not served — said at once, not counted as a
try); „Vilniaus gatvė" is a street, not the city Vilnius.
"""

import pytest

from .helpers import _agent

FUNCTION = "Vietovės paieška"


# --- from test_address_resolver.py ---


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


class TestFullRecoveryPath:
    def test_zeimiu_full_address_in_ginkunai(self, resolver):
        r = resolver(city="Ginkūnai", street="Žeimių", house_number="12", apartment_number="6")
        assert r["success"] is True
        assert r["customer_id"] == "CUST109"


# --- from test_identification_rules.py ---


class TestCitySuggestionWiring:
    """Gyva T-5: „Žeimių g. yra Ginkūnuose" + kliento „taip" → miesto slotas
    persijungia, paieška vyksta ten (tikslinimas nėra bandymai)."""

    def test_confirmation_moves_the_city_slot(self, db_connection):
        from tests.calls import hear

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.suggested_city = "Ginkūnai"
        hear(agent, "Taip, Ginkūnuose")
        assert agent.state.identity.profile.city.value == "Ginkūnai"
        assert agent.state.identity.suggested_city is None

    def test_bare_yes_also_moves(self, db_connection):
        from tests.calls import hear

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.suggested_city = "Ginkūnai"
        hear(agent, "Taip taip")
        assert agent.state.identity.profile.city.value == "Ginkūnai"

    def test_other_answer_keeps_suggestion_open(self, db_connection):
        from tests.calls import hear

        agent = _agent()
        agent.state.identity.suggested_city = "Ginkūnai"
        hear(agent, "Palaukite, pasižiūrėsiu dokumentuose")
        assert agent.state.identity.profile.city.value is None
        assert agent.state.identity.suggested_city == "Ginkūnai"


def test_city_not_served_is_instant(db_connection):
    from agent.decide.rules.reply import scripted_words

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    r = scripted_words(agent.state, agent.runtime, "Vilnius, Gedimino prospektas 1")
    assert r and "Šiaulių mieste ir rajone" in r
    assert not agent.state.closing.case_closed
    assert agent.state.identity.address_empty_turns == 0  # ne bandymas
