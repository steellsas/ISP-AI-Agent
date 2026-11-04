"""Kliento pusės gedimas (Andrius, 2026-11-04): internetas iki routerio ateina, o klientui
neveikia. Agentas išsiaiškina, kur nutrūksta (kiti įrenginiai, koks įrenginys, kaip jungiasi),
ir eina universaliomis kopėčiomis — Wi-Fi, laidas, įrenginys, routeris. Žodžius duoda įrangos
katalogas pagal įrenginį ir jo sistemą; sistemos klausiama tik kai klientas „nežino kaip"."""

import sqlite3

import pytest

FUNCTION = "Kliento pusė"

OTHERS_WORK_PHONE = ["Gerai", "Kompiuteryje veikia, telefone ne", "Telefone"]
LADDER_FAILS = ["Įjungtas", "Taip, savo", "Padariau", "Ne, neveikia", "Perkroviau", "Ne, vis tiek"]


def walk(c, turns):
    for text in turns:
        c.say(text)
    return c


def _ticket(ticket_id):
    from agent.db_path import database_path

    conn = sqlite3.connect(database_path())
    try:
        return conn.execute(
            "SELECT ticket_type, details FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
    finally:
        conn.close()


class TestLadders:
    def test_a_card_names_a_ladder_and_gets_its_steps_for_the_device(self):
        from agent.contract import cards

        card = cards.card("healthy_to_router")
        phone = next(s for s in card.solution if "fail_device=phone" in s.when)
        assert phone.steps[0].module == "wifi_state"
        assert phone.steps[0].args == {"device": "phone"}
        assert [s.module for s in phone.steps[-3:]] == ["offer_fix", "escalate", "conclude"]

    def test_a_single_device_reboots_the_router_before_a_ticket(self):
        from agent.contract import cards

        card = cards.card("healthy_to_router")
        single = next(
            s for s in card.solution if s.when == ["fail_scope=single", "fail_device=phone"]
        )
        modules = [s.module for s in single.steps]
        assert modules.index("reboot") < modules.index("escalate") == len(modules) - 1

    def test_how_words_follow_the_callers_system(self):
        from agent.contract.schema import ModuleCall
        from agent.modules import how_words

        call = ModuleCall(module="wifi_state", args={"device": "phone"})
        assert "Nubraukite" in how_words(call, model="android")
        assert "Nustatymai" in how_words(call, model="iphone")
        assert how_words(call, model=None)  # the basic phone still has words


@pytest.mark.parametrize(
    ("detector", "said", "label"),
    [
        ("switched", "Disable parašyta", "no"),
        ("switched", "Pilkas mygtukas", "no"),
        ("switched", "Neįjungtas", "no"),
        ("switched", "Įjungtas, mėlynas", "yes"),
        ("wifi_network", "Prisijungęs prie kaimyno", "other"),
        ("wifi_network", "Taip, prie savo", "own"),
    ],
)
def test_the_screen_words_are_read(detector, said, label):
    from agent.perceive import detectors

    assert getattr(detectors, f"detect_{detector}")(said) == label


def test_the_system_is_read_from_the_brand():
    from agent.perceive.detectors import detect_device_os

    assert detect_device_os("Samsung", "phone") == "android"
    assert detect_device_os("ajfonas", "phone") == "iphone"
    assert detect_device_os("Windows dešimt", "computer") == "windows"


def test_wifi_switched_off_is_found_and_solved_without_a_ticket(diagnosing):
    """Wi-Fi išjungtas: „disable" yra radinys, įjungus — išspręsta su priežastimi"""
    c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, "Disable parašyta"])
    assert c.state.case.facts["wifi_on"] == "no" and c.rule == "case.wifi_enable"
    walk(c, ["Įjungiau", "Taip, veikia"])
    assert c.rule == "case.resolved"
    assert c.state.case.cause == "pack.healthy_to_router.cause.wifi_off"
    assert not c.state.ticket.ticket_id and not c.state.ticket.stage


def test_how_asks_the_system_once_then_says_where_to_tap(diagnosing):
    """„Kur man eiti?" — koks telefonas, tada tikslus nurodymas (ne pašalinė tema)"""
    c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, "Kur man reikia eiti?"])
    assert c.rule == "case.how_to_os" and "iPhone" in c.replies[-1]
    c.say("Samsung")
    assert c.rule == "case.how_to" and "Nubraukite" in c.replies[-1]
    c.say("Kaip tai padaryti?")
    assert c.rule == "case.how_to"  # the system is not asked twice
    c.say("Pilkas, dabar paspaudžiau")
    assert c.state.case.facts["wifi_on"] == "no"


def test_others_work_and_help_declined_ends_without_a_ticket(diagnosing):
    """Kituose veikia, kopėčios nepadėjo, pagalbos nenori — paaiškinta, nieko neregistruota"""
    c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS])
    assert c.rule == "case.offer_fix"
    c.say("Ne, nereikia")
    assert c.rule == "case.conclude" and "nieko neregistruoju" in c.replies[-1]
    assert c.state.closing.closed_reason == "inform"
    assert not c.state.ticket.ticket_id and not c.state.ticket.stage


def test_paid_help_agreed_registers_its_own_ticket(diagnosing):
    """Sutiko su mokama pagalba — savas tiketo tipas, be „neišspręsime", su nueitu keliu"""
    c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS])
    c.say("Taip, registruokite")
    assert c.rule == "ticket.phone_intro"
    assert "kainą" in c.replies[-1] and "neišspręsime" not in c.replies[-1]
    walk(c, ["Taip, tinka", "Bet kada"])
    ticket_type, details = _ticket(c.state.ticket.ticket_id)
    assert ticket_type == "client_side_help"
    assert "Wi-Fi įjungtas" in details and "perkrovėme įrenginį" in details


def test_a_single_wired_computer_goes_cable_device_router_then_ticket(diagnosing):
    """Vienintelis kompiuteris laidu: laidas, plokštė, perkrovimas, routeris — tada tiketas"""
    c = walk(
        diagnosing("healthy_to_router"),
        ["Gerai", "Neturiu kito, tik vienas kompiuteris", "Kompiuteryje", "Laidu"],
    )
    assert c.rule == "case.cable_seated"
    walk(c, ["Įkištas", "Įjungta, rodo prijungta", "Perkroviau"])
    # „Perkroviau" answers the computer restart — it does not skip to the router.
    assert c.rule == "case.verify" and "reboot" not in c.state.case.worked
    walk(c, ["Ne, neveikia", "Taip, galiu", "Perkroviau routerį", "Ne, vis tiek ne"])
    assert "reboot" in c.state.case.worked
    assert c.state.ticket.reason is None or c.state.ticket.reason == "nebaigtas"
    assert c.rule in ("case.summary", "ticket.phone_intro")
