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
        "ticket",
        True,
        id="mūsų tinklo gedimas → tiketas",
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


@pytest.mark.xfail(
    strict=True,
    reason="ragelio tinklas tikrina telemetrijos `verdict`, kurio nebėra — padėjus ragelį vidury taisymo įrašoma „išspręsta“",
)
def test_a_hang_up_mid_fix_on_a_down_line_is_not_resolved(diagnosing):
    """Padėjo ragelį vidury taisymo, linija neveikia — ne „išspręsta“"""
    c = diagnosing("router_hung")
    for text in ["Gerai", "Taip, galiu prieiti"]:
        c.say(text)
    row = _end(c)
    assert row["outcome"] != "resolved"


@pytest.mark.xfail(
    strict=True,
    reason="tas pats ragelio tinklas — patvirtinta pabaiga vidury taisymo įrašoma „išspręsta“",
)
def test_a_confirmed_goodbye_mid_fix_is_not_resolved(diagnosing):
    """Patvirtino pabaigą vidury taisymo — ne „išspręsta“"""
    c = diagnosing("router_hung")
    for text in ["Gerai", "Viso gero", "Taip"]:
        c.say(text)
    row = _end(c)
    assert row["outcome"] != "resolved"
