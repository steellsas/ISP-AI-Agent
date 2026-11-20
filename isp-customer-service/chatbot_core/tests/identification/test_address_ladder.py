"""Adreso laiptai (#76, #77 — live 2026-11-20): miestas → (rajonas → kaimas) → gatvė → namas.

A place is a step, never a miss; an unrecognised street is narrowed (where, then the street
again) before the account code; „neturiu kodo" does not end the call while the address is
still being built.
"""

from tests.calls import hear

from .helpers import _agent

FUNCTION = "Adreso laiptai"


def _caller(agent_question: str):
    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.intake.anamnesis_asked = True
    agent.state.messages.append({"role": "assistant", "content": agent_question})
    return agent


def _say(agent, text):
    from agent.decide.rules.reply import scripted_words

    hear(agent, text)
    reply = scripted_words(agent.state, agent.runtime, text)
    if reply:
        agent.state.messages.append({"role": "assistant", "content": reply})
    return reply


def test_the_city_is_a_step_not_a_miss(db_connection):
    """Call 0009: „Šiauliai" counted as an unrecognised address."""
    agent = _caller("Koks adresas?")
    r = _say(agent, "Šiauliai")
    assert r and "gatvė" in r and "namo" in r
    assert agent.state.identity.address_unrecognized_turns == 0
    assert agent.state.identity.profile.city.value == "Šiauliai"


def test_a_garbled_street_in_a_known_city_is_asked_again(db_connection):
    """Call 0009: „Vylinaus." went straight to the account code."""
    agent = _caller("Koks adresas?")
    _say(agent, "Šiauliai")
    r = _say(agent, "Vylinaus.")
    assert r and "dar kartą" in r
    assert "kodą" not in r
    assert not agent.state.identity.account_code_mode


def test_an_unknown_street_asks_city_or_district_then_the_village(db_connection):
    agent = _caller("Koks adresas?")
    r1 = _say(agent, "Kosmonautų alėja 7")
    assert r1 and "Šiaulių mieste, ar Šiaulių rajone" in r1
    r2 = _say(agent, "Šiaulių rajone")
    assert r2 and "kaimas" in r2
    r3 = _say(agent, "Ginkūnai")
    assert r3 and "Ginkūnai" in r3 and "gatvė" in r3
    assert agent.state.identity.profile.city.value == "Ginkūnai"


def test_district_with_its_village_goes_to_the_street(db_connection):
    agent = _caller("Ar adresas Šiaulių mieste, ar Šiaulių rajone?")
    r = _say(agent, "Šiaulių rajonas, Ginkūnų kaimas")
    assert r and "Ginkūnai" in r and "gatvė" in r


def test_the_code_comes_only_after_the_street_was_narrowed(db_connection):
    """The rung alone (a dictated house number resets the counter in perceive; there the
    resolver's own failure count leads to the code)."""
    from agent.decide.rules.reply import scripted_words

    agent = _caller("Koks adresas?")
    r1 = scripted_words(agent.state, agent.runtime, "Kosmonautų alėja 7")
    r2 = scripted_words(agent.state, agent.runtime, "Kosmonautų alėja septyni")
    assert "kodą" not in (r1 or "") and "kodą" not in (r2 or "")
    r3 = scripted_words(agent.state, agent.runtime, "Sakau — Kosmonautų alėja 7")
    assert r3 and "abonento kodą" in r3


def test_no_code_with_the_street_found_asks_the_house(db_connection):
    """Call 0009: „Mano adresas Vilniaus gatvė, Šiauliai. Neturiu galimybės abonento kodą."
    closed the call with the street just found."""
    agent = _caller("Ar galite pasakyti abonento kodą?")
    agent.state.identity.account_code_mode = True
    r = _say(agent, "Mano adresas Vilniaus gatvė, Šiauliai. Neturiu galimybės abonento kodą.")
    assert not agent.state.closing.case_closed
    assert r and "namo numeris" in r and "Vilniaus" in r
    assert not agent.state.identity.account_code_mode


def test_no_code_and_no_address_yet_asks_the_address(db_connection):
    agent = _caller("Ar galite pasakyti abonento kodą?")
    agent.state.identity.account_code_mode = True
    r = _say(agent, "Neturiu jokio kodo")
    assert not agent.state.closing.case_closed
    assert r and "adresą" in r
