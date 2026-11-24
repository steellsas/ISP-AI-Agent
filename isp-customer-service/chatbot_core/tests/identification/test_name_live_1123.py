"""Vardo klaidos (#84, #85 — live 2026-11-23):
- a name given in the opening („čia Aldonas…") skipped „Išgirdau — Aldona. Ar teisingai?",
  and the model asked about router lights of its own;
- „Taip, dėl šio adreso, iš kur žinot?" took the turn, the name was never asked, and the next
  sentence „Taip, dėl V. 29 Šiauliai" became the name „Šiauliai";
- „Aš skambinau dėl Vilniaus gatvės" became „Vilniaus"; „Teiks." (tiks) became „Teiks";
  „Tomo vardu sudaryta" became „Malonu, Tomo!".
"""

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
