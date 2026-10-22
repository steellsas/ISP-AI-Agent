"""Kelios sutartys name — two contracts, no flats: the surname decides (T-6); a wrong surname
reveals no registered name; clarifying turns are not counted as tries.
"""

import pytest

from .helpers import _agent

FUNCTION = "Kelios sutartys name"


SURNAMES = [
    pytest.param("Petraitis", "CUST107", id="pavardė tiksli"),
    pytest.param("Kazlauskas", "CUST108", id="kita sutartis name"),
    pytest.param("Tetraitis", "CUST107", id="T-6R darkyta pavardė"),
]


@pytest.mark.parametrize(("surname", "customer"), SURNAMES)
def test_the_surname_picks_the_contract(resolver, surname, customer):
    """Pavardė parenka sutartį"""
    r = resolver(city="Šiauliai", street="Dainų", house_number="7", surname=surname)
    assert r["success"] is True and r["customer_id"] == customer


# --- from test_address_resolver.py ---


def test_house_without_flats_two_contracts_asks_surname(resolver):
    """Dainų g. 7: two contracts, no flats -> surname disambiguation."""
    r = resolver(city="Šiauliai", street="Dainų", house_number="7")
    assert r["resolution"]["apartment"]["status"] == "required"
    assert "pavard" in r["hint"].lower()


def test_surname_disambiguates(resolver):
    r = resolver(city="Šiauliai", street="Dainų", house_number="7", surname="Petraitis")
    assert r["success"] is True
    assert r["customer_id"] == "CUST107"
    assert r["resolution"]["surname_matched"] is True


def test_surname_mismatch_no_pii_leak(resolver):
    r = resolver(city="Šiauliai", street="Dainų", house_number="7", surname="Jonaitis")
    assert r["success"] is False
    assert r["resolution"]["surname_matched"] is False
    # The hint must not reveal the registered surnames.
    assert "Petraitis" not in r["hint"]
    assert "Kazlauskas" not in r["hint"]


# --- from test_identification_rules.py ---


def test_clarifying_turns_never_count(db_connection):
    """Gyva T-6: pavardės tikslinimas skaitiklių neliečia."""
    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.messages.append(
        {"role": "assistant", "content": "Kokia pavardė, kad galėčiau patvirtinti sutartį?"}
    )
    from agent.decide.rules.identification import _account_code_rung

    for txt in ("Tetraitos", "Petraitis", "Pet raitis sakau"):
        handled, reply = _account_code_rung(agent.state, agent.runtime, agent.state, txt)
        assert handled is False and reply is None
    assert agent.state.identity.address_empty_turns == 0
