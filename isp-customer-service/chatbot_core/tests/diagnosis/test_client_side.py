"""Kliento pusės gedimas (Andrius, 2026-11-04): internetas iki routerio ateina, o klientui
neveikia. Agentas išsiaiškina, kur nutrūksta (kiti įrenginiai, koks įrenginys, kaip jungiasi),
ir eina universaliomis kopėčiomis — Wi-Fi, laidas, įrenginys, routeris. Žodžius duoda įrangos
katalogas pagal įrenginį ir jo sistemą; sistemos klausiama tik kai klientas „nežino kaip"."""

import sqlite3

import pytest

FUNCTION = "Kliento pusė"

# The last answer is to „ar galite dabar pasižiūrėti?" — the guided step starts with it.
OTHERS_WORK_PHONE = ["Gerai", "Kompiuteryje veikia, telefone ne", "Telefone", "Taip, galiu"]
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
        assert [s.module for s in phone.steps[:2]] == ["wifi_ready", "wifi_state"]
        assert phone.steps[1].args == {"device": "phone"}
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
    assert c.rule == "case.cable_ready"
    c.say("Taip, prie jo esu")
    assert c.rule == "case.cable_seated"
    walk(c, ["Įkištas", "Įjungta, rodo prijungta", "Perkroviau"])
    # „Perkroviau" answers the computer restart — it does not skip to the router.
    assert c.rule == "case.verify" and "reboot" not in c.state.case.worked
    walk(c, ["Ne, neveikia", "Taip, galiu", "Perkroviau routerį", "Ne, vis tiek ne"])
    assert "reboot" in c.state.case.worked
    assert c.state.ticket.reason is None or c.state.ticket.reason == "nebaigtas"
    assert c.rule in ("case.summary", "ticket.phone_intro")


class TestGuidedSolution:
    """Sprendimas vedamas po žingsnį ir neskubant (Andrius, 2026-11-04)."""

    def test_the_guided_step_says_what_we_check_and_asks_if_they_can(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE[:-1])
        assert c.rule == "case.wifi_ready"  # with the finding, so through the narrator
        c.say("Taip, galiu")
        assert c.rule == "case.wifi_state" and "Nustatymai" in c.replies[-1]

    def test_not_looked_yet_is_not_an_answer(self, diagnosing):
        """„Netikrinau, nežinau" nėra „Wi-Fi išjungtas\""""
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE)
        c.say("Aš netikrinau, nežinau")
        assert "wifi_on" not in c.state.case.facts and c.rule != "case.wifi_enable"

    def test_not_done_yet_at_the_check_goes_back_to_the_instruction(self, diagnosing):
        """„Dar neįjungiau" per patikrą — vėl nurodymas, ne „nepavyko\""""
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, "Išjungtas"])
        assert c.rule == "case.wifi_enable"
        c.say("Gerai")
        c.say("Dar neįjungiau, nerandu jungiklio")
        assert c.rule in ("case.wifi_enable", "case.how_to", "case.how_to_os")
        assert "restored" not in c.state.case.facts
        assert c.state.case.cause is None and not c.state.ticket.stage

    def test_the_guided_pace_waits_longer_and_lets_the_caller_decide(self, diagnosing):
        """Tušti ėjimai: ne tiketas po dviejų, o po penkių — parašytas pasiūlymas"""
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE)
        rules = []
        for _ in range(6):
            c.say("Hmm")
            rules.append(c.rule)
        assert "case.guided_offer" in rules and "case.last_chance" not in rules
        assert not c.state.ticket.stage
        assert "meistras" in c.replies[rules.index("case.guided_offer") - 6]

    def test_cannot_now_at_the_guided_step_takes_the_later_path(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE[:-1])
        c.say("Ne, dabar negaliu, esu darbe")
        assert c.state.case.facts.get("reachable") == "no"
        assert not c.state.ticket.stage


class TestAnalysisPace:
    """Analizė neskuba: „patikrinsiu" nėra neatsakymas, vėlyvas atsakymas perrenka šaką."""

    def test_going_to_check_is_not_an_unanswered_question(self, diagnosing):
        c = diagnosing("healthy_to_router")
        walk(c, ["Gerai", "Nežinau, patikrinsiu", "Mhm", "Palaukit, žiūriu"])
        assert "fail_scope" not in c.state.case.assumed
        assert c.state.case.awaiting == "fail_scope"

    def test_a_late_answer_chooses_the_branch_again(self, diagnosing):
        """Prielaida „vienintelis", paskui „kompiuteryje veikia" — šaka „kituose veikia\""""
        c = diagnosing("healthy_to_router")
        walk(c, ["Gerai", "Nežinau", "Nežinau", "Telefone"])
        assert c.state.case.facts.get("fail_scope") == "single"
        c.say("Aa, kompiuteryje veikia, tik telefone ne")
        from agent.contract import cards

        assert c.state.case.facts["fail_scope"] == "one"
        branch = cards.card("healthy_to_router").solution[c.state.case.solution]
        assert "fail_scope=one" in branch.when

    def test_the_branch_starts_by_saying_what_was_understood(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE[:-1])
        assert c.rule == "case.wifi_ready"
        assert c.replies[-1].startswith("Supratau — kituose įrenginiuose internetas veikia")
        assert c.replies[-1].endswith("Ar galite dabar pasižiūrėti telefono nustatymuose?")

    def test_the_system_said_in_passing_is_kept(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, "Čia Samsung, nežinau kur"])
        assert c.state.case.facts.get("device_os") == "android"
        assert c.rule == "case.how_to" and "Nubraukite" in c.replies[-1]


def test_a_fact_is_said_back_without_its_label_twice():
    from agent.decide.rules.case_rule import fact_words

    assert fact_words("wifi_on", "yes") == "Wi-Fi įjungtas"
    assert fact_words("restored", "yes") == ""
