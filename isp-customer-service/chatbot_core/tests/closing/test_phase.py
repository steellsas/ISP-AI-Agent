"""Visa fazė — the end of the call through the real graph: the goodbye, the call complete, and the
one contact record (conversations row) with the outcome derived from the state (D-14)."""

import pytest

FUNCTION = "Visa fazė"

F = "Taip, galiu."


def _end(c):
    c.session.end_session("hangup")
    return c.record()


ENDINGS = [
    pytest.param(
        "router_hung",
        [
            "Gerai",
            "Taip, galiu prieiti",
            "Taip, galiu prieiti",
            "Perkroviau",
            "Taip, veikia",
            "Ne, ačiū",
        ],
        "resolved",
        False,
        id="sutvarkyta → išspręsta",
    ),
    pytest.param(
        "no_mac_observed",
        [
            "Gerai",
            F,
            F,
            "Nedega nė viena",
            "Maitinimo laidas įkištas tvirtai.",
            "Neturiu kompiuterio.",
            "Taip",
            "Taip",
            "Bet kada",
            "Ne, ačiū",
        ],
        "ticket",
        True,
        id="miręs routeris → tiketas",
    ),
    pytest.param(
        "billing_suspended",
        ["Gerai", "Ne, ačiū, viso gero"],
        "informed_debt",
        False,
        id="skola → informuota",
    ),
    pytest.param(
        "active_outage",
        ["Gerai", "Ne, ačiū, viso gero"],
        "informed_outage",
        False,
        id="avarija → informuota",
    ),
    pytest.param(
        "switch_unreachable",
        ["Gerai", "Ne, ačiū"],
        "informed",
        True,
        id="mūsų tinklo gedimas → informuota (tinklo tiketas)",
    ),
    pytest.param(
        "router_hung",
        ["Gerai", "Taip, galiu prieiti", "Ne, nesu namie", "Vakare", "Gerai"],
        "callback",
        False,
        id="namų darbas → perskambins",
    ),
    pytest.param(
        "no_mac_observed",
        [
            "Gerai",
            F,
            F,
            "Nedega nė viena",
            "Maitinimo laidas įkištas tvirtai.",
            "Neturiu kompiuterio.",
        ],
        "ticket",
        True,
        id="padėjo ragelį po sprendimo → tiketas",
    ),
]


@pytest.mark.parametrize(("card", "turns", "outcome", "ticket"), ENDINGS)
def test_the_record_says_how_the_call_ended(diagnosing, card, turns, outcome, ticket):
    """Kontakto įrašas atitinka pabaigą"""
    c = diagnosing(card)
    for text in turns:
        c.say(text)
    row = _end(c)
    assert row and row["outcome"] == outcome and bool(row["ticket_id"]) is ticket
    assert not row["needs_review"]


@pytest.mark.parametrize(
    ("turns", "outcome", "why"),
    [
        pytest.param(
            ["Nu taip", "Nežinau", "Nieko", "Nežinau"],
            "unidentified",
            "not_a_customer",
            id="problemos nepasakė",
        ),
        pytest.param(
            ["Neveikia internetas", "Tilžės gatvė 60"],
            "unidentified",
            "address_not_found",
            id="padėjo ragelį be adreso",
        ),
    ],
)
def test_an_unidentified_call_is_kept_for_review(call, turns, outcome, why):
    """Neidentifikuotas skambutis — įrašas peržiūrai"""
    c = call()
    for text in turns:
        c.say(text)
    row = _end(c)
    assert (row["outcome"], row["unidentified_reason"], row["needs_review"]) == (outcome, why, 1)


def _unfinished(row):
    import sqlite3

    from agent.db_path import database_path

    conn = sqlite3.connect(database_path())
    try:
        kind = conn.execute(
            "SELECT ticket_type FROM tickets WHERE ticket_id = ?", (row["ticket_id"],)
        ).fetchone()
    finally:
        conn.close()
    return (row["outcome"], row["needs_review"], row["review_reason"], kind and kind[0])


UNFINISHED = ("unfinished", 1, "unfinished", "call_unfinished")


def test_a_hang_up_mid_fix_on_a_down_line_is_unfinished(diagnosing):
    """Padėjo ragelį vidury taisymo — nebaigtas, žmogus perskambins"""
    c = diagnosing("router_hung")
    for text in ["Gerai", "Taip, galiu prieiti"]:
        c.say(text)
    row = _end(c)
    assert _unfinished(row) == UNFINISHED
    assert c.state.ticket.reason == "nebaigtas"


def test_a_confirmed_goodbye_mid_fix_is_unfinished(diagnosing):
    """Patvirtino pabaigą vidury taisymo — nebaigtas, ne „išspręsta“"""
    c = diagnosing("router_hung")
    for text in ["Gerai", "Viso gero", "Taip"]:
        c.say(text)
    row = _end(c)
    assert _unfinished(row) == UNFINISHED


def test_a_hang_up_after_veikia_before_the_end_is_resolved(diagnosing):
    """Klientas patvirtino „veikia“ ir padėjo ragelį — išspręsta (patvirtino klientas)"""
    c = diagnosing("router_hung")
    for text in [
        "Gerai",
        "Taip, galiu prieiti",
        "Taip, galiu prieiti",
        "Perkroviau",
        "Taip, veikia",
    ]:
        c.say(text)
    row = _end(c)
    assert row["outcome"] == "resolved" and not row["ticket_id"]
