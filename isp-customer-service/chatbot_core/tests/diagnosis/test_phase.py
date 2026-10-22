"""Visa fazė — from the identified caller to the conclusion, through the real graph, one demo
customer per card (tests/phases.py; the `diagnosing` fixture starts right after
identification, the next turn hears the findings).

A conclusion is one of three: the fault is solved on the phone, the caller is told the news
(debt, outage, a fault in our network — the latter registers the ticket itself), or the call
goes to the ticket dialogue with the card's reason. The speaking LLM is faked: a test checks
what the ENGINE did — the card, the steps, the conclusion — and the engine's own phrases.

`FIRST` — the answer to the first question after the findings is given twice: the engine's
own reader does not yet know that question was asked (see the known gap below); in a real
call the model's read picks it up.
"""

import pytest

FUNCTION = "Visa fazė"

FIRST = "Taip, galiu."


def walk(c, turns):
    for text in turns:
        c.say(text)
    return c


# (card, the caller's turns after the findings, the conclusion rule, the words in its reply)
TO_A_TICKET = [
    pytest.param(
        "no_mac_observed",
        [
            "Gerai",
            FIRST,
            FIRST,
            "Nedega nė viena",
            "Maitinimo laidas įkištas tvirtai.",
            "Neturiu kompiuterio.",
            "Taip",
        ],
        "naujas maršrutizatorius",
        id="įrenginio nematyti",
    ),
    pytest.param(
        "link_down_local",
        ["Gerai", FIRST, FIRST, "Dega žalia", "Perkišau laidą", "Neveikia"],
        "signalas iš linijos neateina",
        id="linija neaktyvi",
    ),
    pytest.param(
        "crc_errors",
        ["Gerai", FIRST, FIRST, "Patikrinau, laidas sveikas, tvirtai įkištas", "Neveikia"],
        "pažeistas laidas",
        id="klaidos linijoje",
    ),
    pytest.param(
        "healthy_to_router",
        ["Gerai", "Visuose įrenginiuose", "Taip, perkroviau"],
        "Registruoju meistrą",
        id="sveika iki routerio",
    ),
]


@pytest.mark.parametrize(("card", "turns", "reason"), TO_A_TICKET)
def test_what_the_phone_cannot_fix_goes_to_a_ticket(diagnosing, card, turns, reason):
    """Ko nepataisysime telefonu — į tiketą su priežastimi"""
    c = walk(diagnosing(card), turns)
    assert c.state.case.fault == card
    assert c.rule == "ticket.phone_intro"
    assert reason in c.replies[-1] and "neišspręsime" in c.replies[-1]


@pytest.mark.parametrize(
    ("card", "turns"),
    [
        pytest.param(
            "router_hung",
            ["Gerai", "Taip, galiu prieiti", "Perkroviau", "Taip, veikia"],
            id="sustingęs routeris: perkrauta",
        ),
        pytest.param(
            "foreign_mac",
            ["Gerai", "Taip, pasikeičiau routerį", "Gerai", "Taip, veikia"],
            id="svetimas routeris: pririšta",
        ),
    ],
)
def test_what_the_phone_can_fix_is_solved(diagnosing, card, turns):
    """Ką galima pataisyti telefonu — išsprendžiama"""
    c = walk(diagnosing(card), turns)
    assert c.state.case.fault == card and c.rule == "case.resolved"
    assert c.state.closing.closed_reason == "resolved" and c.state.ticket.ticket_id is None


@pytest.mark.parametrize(
    ("card", "news", "ticket"),
    [
        pytest.param("billing_suspended", "Skola 49 eurai 98 centai", False, id="skola"),
        pytest.param("active_outage", "tinklo avarija", False, id="avarija"),
        pytest.param("switch_unreachable", "gedimą užregistravau", True, id="mazgas nepasiekiamas"),
        pytest.param("node_fault_unregistered", "gedimą užregistravau", True, id="gedimas tinkle"),
    ],
)
def test_news_is_told_and_the_call_can_end(diagnosing, card, news, ticket):
    """Žinia pasakoma, ir pokalbį galima baigti"""
    c = diagnosing(card)
    told = c.say("Gerai")
    assert c.rule == "inform.template" and news in told
    assert c.state.diagnosis.news_delivered and bool(c.state.ticket.ticket_id) is ticket
    c.say("Ne, ačiū, viso gero")
    assert c.state.closing.case_closed and not c.state.case.fault  # nothing was diagnosed


def test_the_guide_starts_for_a_silent_router(diagnosing):
    """Routeris neprašo adreso — pradedamas vedimas per nustatymus"""
    c = walk(
        diagnosing("dhcp_silent"),
        ["Gerai", "Turiu telefoną.", "Turiu telefoną.", "Pabandykim kartu."],
    )
    assert c.state.case.fault == "dhcp_silent" and c.rule == "case.guide"


def test_no_question_before_the_reboot_of_a_hung_router(diagnosing):
    """Sustingusiam routeriui — jokių klausimų prieš perkrovimą"""
    c = diagnosing("router_hung")
    c.say("Gerai")
    assert c.state.case.fault == "router_hung" and c.state.case.awaiting == "reachable"


@pytest.mark.xfail(
    strict=True,
    reason="atsakymą į pirmą klausimą po radinio skaito tik modelis — variklis klausia dar kartą",
)
def test_the_answer_to_the_first_question_is_read_by_the_engine(diagnosing):
    """Atsakymas į pirmą klausimą po radinio — perskaitomas be modelio"""
    c = diagnosing("no_mac_observed")
    c.say("Gerai")  # the findings and „Ar galite dabar prieiti prie routerio?"
    c.say(FIRST)
    assert c.rule == "case.check_lights"
