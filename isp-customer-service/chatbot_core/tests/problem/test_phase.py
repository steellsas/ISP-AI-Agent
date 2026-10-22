"""Visa fazė — from the greeting to "the agent knows what the call is about", through the real
graph (tests/phases.py; the speaking LLM faked, the model classifier off — the engine's own
reader decides). What each kind of call leads to next: a fault goes to identification and the
line check; a request goes to identification and a ticket, without checking the line; no
problem at all ends politely.
"""

import pytest

FUNCTION = "Visa fazė"


def test_a_greeting_gets_the_problem_question(call):
    """Pasisveikinimas — klausia, kas atsitiko"""
    c = call()
    reply = c.say("Laba diena")
    assert c.rule == "identification.ask_problem" and "kokia problema" in reply
    assert c.state.intake.problem_type is None


def test_the_problem_leads_to_the_address(call):
    """Problema → adreso klausimas"""
    c = call()
    c.say("Laba diena")
    reply = c.say("Neveikia internetas")
    assert c.state.intake.problem_type == "internet_down"
    assert "Koks adresas?" in reply


def test_a_known_number_gets_the_address_offered(call):
    """Žinomas numeris — problema → adreso pasiūlymas"""
    c = call("+37060020112")
    reply = c.say("Neveikia internetas")
    assert c.state.intake.problem_type == "internet_down"
    assert "Ar skambinate dėl Vilniaus g. 33, butas 2?" in reply


def test_problem_and_address_in_one_breath(call):
    """Problema ir adresas vienu sakiniu"""
    c = call()
    c.say("Neveikia internetas, Tilžės gatvė 60, butas 7")
    p = c.identity.profile
    assert c.state.intake.problem_type == "internet_down"
    assert (p.street.value, p.house.value, p.apartment.value) == ("Tilžės g.", "60", "7")


def test_when_and_after_what_are_kept_from_the_opening(call):
    """Kada ir po ko — iš pirmo sakinio"""
    c = call()
    c.say("Neveikia internetas nuo vakar vakaro, po audros")
    assert (c.state.intake.anamnesis_when, c.state.intake.anamnesis_trigger) == (
        "yesterday",
        "storm",
    )


@pytest.mark.parametrize(
    ("said", "purpose"),
    [
        pytest.param("Neveikia televizija", "tv", id="TV gedimas"),
        pytest.param("Internetas labai lėtas", "internet_slow", id="lėtas internetas"),
        pytest.param("Neveikia internetas", "internet_down", id="nėra interneto"),
    ],
)
def test_a_fault_goes_to_identification(call, said, purpose):
    """Gedimas → identifikacija"""
    c = call("+37060020112")
    c.say(said)
    c.say("Taip")
    assert c.state.intake.problem_type == purpose
    assert c.identity.customer_id == "CUST112" and c.rule == "identification.caller_name"


def test_a_billing_question_is_registered_not_diagnosed(call):
    """Sąskaitos klausimas — registruojamas, linija netikrinama"""
    c = call("+37060020112")
    c.say("Skambinu dėl sąskaitos")
    c.say("Taip")
    reply = c.say("Paulius")
    assert c.state.intake.problem_type == "billing"
    assert c.rule == "ticket.phone_intro" and "užregistruosiu" in reply
    assert "diagnose_connection" not in c.tools


@pytest.mark.xfail(
    strict=True, reason="prašymui sakoma „patikrinsiu ryšį“, nors linija netikrinama"
)
def test_a_request_is_not_promised_a_line_check(call):
    """Prašymui nežadama patikrinti ryšio"""
    c = call("+37060020112")
    reply = c.say("Skambinu dėl sąskaitos")
    assert "patikrinsiu ryšį" not in reply


@pytest.mark.xfail(strict=True, reason="„nutraukti sutartį“ skaitoma kaip „baigti pokalbį“")
def test_ending_the_contract_is_a_request_not_a_goodbye(call):
    """„Nutraukti sutartį“ — prašymas, ne atsisveikinimas"""
    c = call("+37060020112")
    c.say("Noriu nutraukti sutartį")
    assert c.rule != "dialog.confirm_end"
    assert c.state.intake.problem_type == "disconnection"


def test_no_problem_said_ends_politely_after_four_tries(call):
    """Problemos nepasako — po 4 bandymų mandagiai baigia"""
    c = call()
    c.say("Laba diena")  # a greeting is not a try
    c.say("Nu taip")
    c.say("Nežinau")
    warned = c.say("Nieko")
    assert "turėsiu baigti pokalbį" in warned and not c.state.closing.case_closed
    closed = c.say("Nežinau")
    assert c.state.closing.case_closed and "baigiu pokalbį" in closed
    assert c.state.ticket.ticket_id is None and c.identity.customer_id is None
