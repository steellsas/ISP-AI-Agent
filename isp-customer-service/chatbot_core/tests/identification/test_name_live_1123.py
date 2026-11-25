"""Vardo klaidos (#84, #85 — live 2026-11-23):
- a name given in the opening („čia Aldonas…") skipped „Išgirdau — Aldona. Ar teisingai?",
  and the model asked about router lights of its own;
- „Taip, dėl šio adreso, iš kur žinot?" took the turn, the name was never asked, and the next
  sentence „Taip, dėl V. 29 Šiauliai" became the name „Šiauliai";
- „Aš skambinau dėl Vilniaus gatvės" became „Vilniaus"; „Teiks." (tiks) became „Teiks";
  „Tomo vardu sudaryta" became „Malonu, Tomo!".
"""

import pytest

FUNCTION = "Vardo klaidos"

TOMAS = "+37060020101"  # CUST101 — the holder is Tomas
ALDONA = "+37060020109"  # CUST109 — the holder is Aldona
GIEDRIUS = "+37060012353"  # CUST009 — the holder is Giedrius


def test_a_name_from_the_opening_is_said_back_first(call):
    c = call(ALDONA)
    c.say("Labą dieną, čia Aldonas Kamin, neveikia internetas.")
    said = c.say("Taip, dėl šio adreso skambinu.")
    assert c.rule == "identification.name_confirm"
    assert "Išgirdau — Aldona" in said and "lemput" not in said.lower()


def test_how_did_you_know_is_answered_with_the_name_question(call):
    c = call(GIEDRIUS)
    c.say("Neveikia internetas")
    said = c.say("Taip, dėl šio adreso skambinu, iš kur žinot?")
    assert c.rule == "identification.caller_name" and "vardas" in said
    c.say("Taip, dėl V. 29 Šiauliai.")
    assert c.identity.caller_name is None  # an address sentence names nobody — asked again


def test_a_street_is_not_a_name(call):
    c = call(TOMAS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Aš skambinau dėl Vilniaus gatvės.")
    assert c.identity.caller_name is None


def test_teiks_is_a_yes(call):
    c = call(TOMAS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Tomas mano vardas.")
    c.say("Teiks.")
    assert c.identity.caller_name == "Tomas"
    assert not c.identity.holder_clarify_open


def test_a_name_still_stands_next_to_a_city():
    from agent.perceive.caller import extract_caller_name

    assert extract_caller_name("Mano vardas Tomas, gyvenu Šiauliuose") == "Tomas"
    assert extract_caller_name("Jonas") == "Jonas"
    assert extract_caller_name("Taip, dėl V. 29 Šiauliai.") is None


def test_the_contract_name_in_the_genitive_takes_the_holders_spelling(call):
    c = call(TOMAS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Petras")
    c.say("Taip")
    assert c.identity.holder_clarify_open
    c.say("Tomo vardu sudaryta, tai mano vardu sudaryta sutartis.")
    assert c.identity.caller_name == "Tomas"


# --- live 2026-11-24 ---------------------------------------------------------------------


def test_a_name_after_the_city_is_taken():
    """„Šiauliuose, jo, Šiauliai. Giedrius, manau" — the name was asked twice more."""
    from agent.perceive.caller import extract_caller_name

    assert extract_caller_name("Šiauliuose, jo, Šiauliai. Giedrius, manau,") == "Giedrius"


def test_whose_the_contract_is_asks_if_it_is_them(call):
    """„Tomo vardu ten sutartis su Daryto." became „Išgirdau — Ten"."""
    c = call(TOMAS)
    c.say("Neveikia internetas")
    c.say("Taip")
    said = c.say("Tomo vardu ten sutartis su Daryto.")
    assert c.rule == "identification.name_confirm"
    assert said == "Supratau, sutartis Tomo vardu. O jūs pats — Tomas?"
    c.say("Taip")
    assert c.identity.caller_name == "Tomas" and not c.identity.holder_clarify_open


def test_a_misheard_tinka_is_a_yes_not_a_name(call):
    """„Teikti sengą." to „Išgirdau — Giedrius. Ar teisingai?" became the name „Teikti",
    and the ticket's contact with it (live 2026-11-24)."""
    c = call(GIEDRIUS)
    c.say("Neveikia internetas")
    c.say("Taip")
    c.say("Mano vardas yra Giedrius.")
    c.say("Teikti sengą.")
    assert c.identity.caller_name == "Giedrius"
    assert not c.identity.holder_clarify_open


def test_ten_is_no_name():
    from agent.perceive.caller import extract_caller_name

    assert extract_caller_name("Vardu ten.") is None


# --- „Ne" to the offered address (live 2026-11-23, call 6) ---------------------------------

OFFERED = "+37060020105"  # the number's address is offered first


@pytest.mark.parametrize(
    ("said", "reading"),
    [
        ("Ne. Nel... nedėl šios adresos skambinų.", "no"),
        ("Taip, palauk.", None),
        ("Taip, dėl šio adreso.", "yes"),
    ],
)
def test_the_offer_answer_is_read(said, reading):
    from agent.perceive.detectors import detect_address_confirm

    assert detect_address_confirm(said) == reading


def test_no_to_the_offered_address_asks_which(call):
    c = call(OFFERED)
    c.say("Neveikia internetas")
    said = c.say("Ne.")
    assert said == "Supratau. Dėl kokio adreso skambinate?"
    assert c.identity.customer_id is None
