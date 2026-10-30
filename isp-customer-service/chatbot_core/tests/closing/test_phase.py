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


@pytest.mark.parametrize(
    "asked", ["Tai koks gedimas?", "O koks šiek gėdimas?", "Kodas nevyk internetas.", "Nesupratau"]
)
def test_a_question_about_the_fault_gets_a_short_reminder(diagnosing, asked):
    """Klausimas apie gedimą po žinios — trumpas priminimas, neatsisveikina"""
    c = diagnosing("active_outage")
    c.say("Gerai")
    for _ in range(3):
        reply = c.say(asked)
        assert c.rule == "inform.remind" and reply.startswith("Primenu — tai tinklo avarija")
        assert "paskambinkite mums" in reply and reply.endswith("Ar dar kuo galiu padėti?")
    assert not c.state.closing.case_closed


def test_cut_news_is_finished_not_repeated(diagnosing):
    """Nutraukta žinia užbaigiama vieną kartą, ne kartojama du kartus"""
    from agent.delivery import apply_delivery

    c = diagnosing("active_outage")
    c.say("Gerai")
    news = c.state.messages[-1]["content"]
    c.session._write_between_turns(
        lambda state, rt: apply_delivery(state, rt, ["Ačiū!", news.split("Ačiū! ", 1)[1]], 1)
    )
    reply = c.say("Kas atsitiko?")
    assert c.rule == "inform.finish"
    assert reply.count("Patikrinau") == 1 and reply.endswith("Ar dar kuo galiu padėti?")


def test_name_fragments_do_not_use_up_the_reminder(diagnosing):
    """Vardo nuotrupos nesuvalgo priminimo"""
    c = diagnosing("active_outage")
    c.say("Gerai")
    c.say("Ramana, o sako tu")
    c.say("Rasam anavardas.")
    c.say("Tai koks gedimas?")
    assert c.rule == "inform.remind"
    c.say("Kodas nevyk internetas.")
    assert c.rule == "inform.remind" and not c.state.closing.case_closed


def test_a_disputed_payment_goes_to_the_accounting_with_its_details(diagnosing):
    """Ginčas: kada, kiek, kaip mokėjo → pasiūlymas → tiketas su faktais buhalterijai"""
    c = diagnosing("billing_suspended")
    c.say("Gerai")
    asked = c.say("Žinokit, aš sumokėjau liepos mėnesį 40 eurų.")
    assert c.rule == "inform.debt_claim" and "kokiu būdu" in asked and "kada" not in asked
    offer = c.say("Pavedimu per Swedbank.")
    assert "(liepos mėn., banko pavedimu, per Swedbank, 40 €)" in offer and offer.endswith(
        "Ar registruoti?"
    )
    explained = c.say("O kodėl jūs nematote mano mokėjimo?")
    assert c.rule == "inform.debt_explain" and explained.endswith("Ar registruoti?")
    for said in ("Pasižiūrėkit.", "Taip, tinka.", "Bet kada"):
        c.say(said)
    assert c.state.ticket.ticket_id
    from agent.tools import get_db

    with get_db().cursor() as cur:
        cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (c.state.ticket.ticket_id,))
        text = dict(cur.fetchone())["details"]
    assert text.startswith("Skolos ginčas. Klientas atjungtas už skolą 49")
    assert "Kliento teiginys: mokėjo liepos mėn., banko pavedimu, per Swedbank, 40 €" in text
    assert "Kliento klausimai: O kodėl jūs nematote mano mokėjimo? Kontaktas" in text


def test_the_call_is_not_ended_while_the_caller_talks(diagnosing):
    """Po ribos agentas klausia „Ar dar kuo galiu padėti?", o ne atsisveikina"""
    c = diagnosing("billing_suspended")
    c.say("Gerai")
    for said in ("Labas", "Kažkas", "Dar kažkas"):
        c.say(said)
    assert not c.state.closing.case_closed
    c.say("Ne, viso gero")
    assert c.state.closing.case_closed
