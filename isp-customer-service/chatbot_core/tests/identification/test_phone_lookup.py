"""Paieška pagal numerį — a known number makes the agent OFFER the address (T-1, T-2); nothing is
committed and nothing about the account is said before the caller confirms.
"""

import pytest

FUNCTION = "Paieška pagal numerį"


def test_a_known_number_gets_its_address_offered(call):
    """T-1 žinomas numeris — adresas pasiūlomas"""
    c = call("+37060020112")
    assert c.identity.phone_candidate["customer_id"] == "CUST112"
    reply = c.say("Laba diena, neveikia internetas")
    assert "Ar skambinate dėl Vilniaus g. 33, butas 2?" in reply
    assert c.identity.customer_id is None  # offered, not taken


def test_an_unknown_number_is_asked_for_the_address(call):
    """Nežinomas numeris — klausia adreso"""
    c = call("unknown")
    assert c.identity.phone_candidate is None
    assert "Koks adresas?" in c.say("Neveikia internetas")


def test_a_no_to_the_offer_takes_nothing(call):
    """„Ne“ pasiūlytam adresui — nieko nepriskiria"""
    c = call("+37060020112")
    c.say("Neveikia internetas")
    c.say("Ne, skambinu dėl kito adreso — Tilžės gatvė 60")
    assert c.identity.customer_id is None
    assert c.identity.profile.street.value == "Tilžės g."


def test_nothing_about_the_account_before_the_yes(call):
    """Iki „taip“ — nė žodžio apie sąskaitą ar avariją"""
    debt = call("+37060020101")  # CUST101 owes 49.98
    outage = call("+37060020102")  # CUST102 lives on Dainų g., an active outage
    for c in (debt, outage):
        c.say("Neveikia internetas")
        heard = c.heard_everything().lower()
        for word in ("skol", "eur", "sustabdyt", "avarij", "outage", "kabel"):
            assert word not in heard, word
    assert outage.identity.held_outage  # held quietly, said only after the confirmation
