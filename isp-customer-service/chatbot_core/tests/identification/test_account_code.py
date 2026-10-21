"""Abonento kodas — heard at any time, normalised from speech, echoed back (A-3R), and a code
that is not in the system is said as heard (T-10, A-3).
"""

import pytest

from .helpers import _agent

FUNCTION = "Abonento kodas"


CODES = [
    pytest.param("AB-10104", "AB-10104", id="pilnas kodas"),
    pytest.param("ab 10104", "AB-10104", id="mažosios, tarpas"),
    pytest.param("10104", "AB-10104", id="tik skaičiai"),
    pytest.param("AB 1 0 1 0 4", "AB-10104", id="skaitmenys po vieną"),
    pytest.param("Mano kodas AB10104", "AB-10104", id="sakinyje, be brūkšnio"),
    pytest.param("Vilniaus g. 29", None, id="adresas nėra kodas"),
    pytest.param("Tilžės 60 butas 7", None, id="adresas su butu nėra kodas"),
    pytest.param("nežinau", None, id="be kodo"),
]


@pytest.mark.parametrize(("said", "code"), CODES)
def test_the_code_is_heard(said, code):
    """Kodas išgirstamas"""
    from agent.decide.rules.identification import _extract_account_code

    assert _extract_account_code(said) == code


# --- from test_identification_rules.py ---


def test_extract_account_code_forms():
    from agent.decide.rules.identification import _extract_account_code

    assert _extract_account_code("Mano kodas AB-10104") == "AB-10104"
    assert _extract_account_code("ab 10104") == "AB-10104"
    assert _extract_account_code("10104") == "AB-10104"
    assert _extract_account_code("Vilniaus g. 29") is None  # adresas ne kodas
    assert _extract_account_code("nežinau") is None


def test_code_heard_anytime_without_mode(db_connection):
    """Kodas girdimas VISADA — klientas gali jį pasakyti nelaukiamas."""
    from agent.decide.rules.reply import scripted_words

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    scripted_words(agent.state, agent.runtime, "Adreso nežinau, bet turiu abonento kodą AB-10104")
    assert agent.state.identity.phone_candidate
    assert agent.state.identity.phone_candidate["customer_id"] == "CUST104"
    assert agent.state.identity.customer_id is None  # adresas SIŪLOMAS, ne prisiimamas


def test_code_mode_passes_content_through(db_connection):
    """KURTUMO fix: adresas/pavardė kodo režime praleidžiami į normalią
    eigą, o ne atsimuša į „kodas atrodo taip"."""
    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.identity.account_code_mode = True
    from agent.decide.rules.identification import _account_code_rung

    handled, reply = _account_code_rung(
        agent.state, agent.runtime, agent.state, "Petraitis, pasižiūrėkit pavardę"
    )
    assert handled is False and reply is None  # praleista — agentas klauso
    handled, reply = _account_code_rung(
        agent.state, agent.runtime, agent.state, "Ginkūnai, Žeimių gatvė 12"
    )
    assert handled is False
    assert agent.state.identity.account_code_mode is False  # režimas tyliai užgeso


class TestCodeHoles:
    """A-banga P3 (gyva #3): perspėjimas įjungia klausymą; įrankis normalizuoja
    STT kodą; „kodą mini be skaičių" gauna scripted pagalbą."""

    def test_warning_arms_listening_then_bare_digits_work(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        scripted_words(agent.state, agent.runtime, "Nežinau adreso")
        r = scripted_words(agent.state, agent.runtime, "Negaliu pasakyti")  # warn
        assert r and "negalėsiu" in r
        assert agent.state.identity.account_code_mode is True
        scripted_words(agent.state, agent.runtime, "10104")
        assert agent.state.identity.phone_candidate
        assert agent.state.identity.phone_candidate["customer_id"] == "CUST104"

    def test_tool_normalizes_stt_garbled_code(self, db_connection):
        import json as _json

        from agent.tools import execute_tool

        r = _json.loads(execute_tool("find_customer", {"account_code": "D10104"}))
        assert r["success"] and r["customer_id"] == "CUST104"
        r = _json.loads(execute_tool("find_customer", {"account_code": "ab 10101"}))
        assert r["success"] and r["customer_id"] == "CUST101"

    def test_code_talk_without_digits_gets_scripted_help(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        r = scripted_words(agent.state, agent.runtime, "Nu, gerai, abonento kodą pasakysiu. A. B.")
        assert r and "penki skaitmenys" in r  # scripted, ne LLM haliucinacija

    def test_found_code_is_echoed_with_address(self, db_connection):
        """A-3 skaidrumas: agentas pasako, KOKĮ kodą išgirdo, ir kartu siūlo
        adresą patvirtinimui — klientas pagauna klaidą prieš einant toliau."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        from agent.decide.rules.identification import _account_code_rung

        handled, r = _account_code_rung(
            agent.state, agent.runtime, agent.state, "Kodas dešimt šimtas keturi, 10104"
        )
        assert handled and r
        assert "Išgirdau kodą" in r and "1 0 1 0 4" in r
        assert "skambinate dėl" in r  # verbatim šerdis — patvirtinimo sargui

    def test_missed_code_is_echoed_too(self, db_connection):
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        from agent.decide.rules.identification import _account_code_rung

        handled, r = _account_code_rung(agent.state, agent.runtime, agent.state, "AB 99999")
        assert handled and r
        assert "Išgirdau kodą" in r and "9 9 9 9 9" in r and "nerandu" in r


# --- from test_address_resolver.py ---


def test_find_customer_by_account_code(db_connection):
    from agent.tools import find_customer

    r = find_customer(account_code="AB-10109")
    assert r["success"] is True
    assert r["customer_id"] == "CUST109"


def test_find_customer_unknown_account_code(db_connection):
    from agent.tools import find_customer

    r = find_customer(account_code="AB-99999")
    assert r["success"] is False
