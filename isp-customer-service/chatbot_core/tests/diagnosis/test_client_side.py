"""Kliento pusės gedimas (Andrius, 2026-11-04/05): internetas iki routerio ateina, o klientui
neveikia. Agentas padeda su tuo įrenginiu, dėl kurio skambina (Wi-Fi arba laidas, perkrovimas);
nepavykus — kiti įrenginiai (tinklų palyginimas) arba routeris; tik tada tiketas. Žodžius duoda
įrangos katalogas pagal įrenginį ir jo sistemą; sistemos klausiama tik kai klientas „nežino kaip"."""

import sqlite3

import pytest

FUNCTION = "Kliento pusė"

# The last answer is to „ar galite dabar pasižiūrėti?" — the guided step starts with it.
OTHERS_WORK_PHONE = ["Gerai", "Kompiuteryje veikia, telefone ne", "Telefone", "Taip, galiu"]
LADDER_FAILS = ["Įjungtas", "Taip, savo", "Padariau", "Ne, neveikia", "Perkroviau", "Ne, vis tiek"]
# The phone's ladder did not help: other devices work, on the same network.
OTHERS_SAME_NETWORK = ["Kompiuteryje veikia", "Taip, tas pats"]


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
        phone = next(s for s in card.solution if s.when == ["fail_device=phone"])
        modules = [s.module for s in phone.steps]
        assert modules[:2] == ["wifi_ready", "wifi_state"]
        assert phone.steps[1].args == {"device": "phone"}
        # The other devices only after the phone's own ladder; the ticket last.
        assert modules.index("device_restart") < modules.index("other_devices")
        assert modules.index("other_devices") < modules.index("wifi_compare")
        assert modules[-1] == "escalate"

    def test_a_single_device_reboots_the_router_before_a_ticket(self):
        from agent.contract import cards

        card = cards.card("healthy_to_router")
        phone = next(s for s in card.solution if s.when == ["fail_device=phone"])
        reboot = next(s for s in phone.steps if s.module == "reboot")
        assert reboot.run_when == ["fail_scope!=one"]
        modules = [s.module for s in phone.steps]
        assert modules.index("reboot") < len(modules) - 1 and modules[-1] == "escalate"

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
    c = walk(
        diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS, *OTHERS_SAME_NETWORK]
    )
    assert c.rule == "case.offer_fix"
    c.say("Ne, nereikia")
    assert c.rule == "case.conclude" and "nieko neregistruoju" in c.replies[-1]
    assert c.state.closing.closed_reason == "inform"
    assert not c.state.ticket.ticket_id and not c.state.ticket.stage


def test_paid_help_agreed_registers_its_own_ticket(diagnosing):
    """Sutiko su mokama pagalba — savas tiketo tipas, be „neišspręsime", su nueitu keliu"""
    c = walk(
        diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS, *OTHERS_SAME_NETWORK]
    )
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
        offer = c.replies[rules.index("case.guided_offer") - 6]
        assert "padėsiu" in offer and "meistr" not in offer  # help, not a technician

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
        assert "fail_device" not in c.state.case.assumed
        assert c.state.case.awaiting == "fail_device"

    def test_a_late_answer_chooses_the_branch_again(self, diagnosing):
        """Prielaida „nepatikslintas įrenginys", paskui „telefone neveikia" — telefono šaka"""
        from agent.contract import cards

        c = walk(diagnosing("healthy_to_router"), ["Gerai", "Nežinau", "Nežinau"])
        assert c.state.case.facts.get("fail_device") == "other"
        c.say("Aa, čia telefone neveikia")
        assert c.state.case.facts["fail_device"] == "phone"
        branch = cards.card("healthy_to_router").solution[c.state.case.solution]
        assert branch.when == ["fail_device=phone"]

    def test_the_branch_starts_by_saying_what_was_understood(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), ["Gerai", "Telefone"])
        assert c.rule == "case.wifi_ready"
        assert c.replies[-1].startswith("Supratau — internetas neveikia telefone.")
        assert c.replies[-1].endswith("Ar galite dabar pasižiūrėti telefono nustatymuose?")

    def test_the_system_said_in_passing_is_kept(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, "Čia Samsung, nežinau kur"])
        assert c.state.case.facts.get("device_os") == "android"
        assert c.rule == "case.how_to" and "Nubraukite" in c.replies[-1]


def test_a_fact_is_said_back_without_its_label_twice():
    from agent.decide.rules.case_rule import fact_words

    assert fact_words("wifi_on", "yes") == "Wi-Fi įjungtas"
    # 2026-11-06: every caller fact has its own prepared phrase (`evidence.said_back`).
    assert fact_words("restored", "yes") == "internetas veikia"
    assert fact_words("device_ready", "yes") == "galite pasižiūrėti dabar"  # finding #56


class TestLiveCall0105:
    """Gyvai 2026-11-05: „neturiu, tik telefoną naudoju", „telefone neveikia" — ir tiketas be
    jokios patikros. Dabar įrenginys perskaitomas iš bet kurio sakinio ir einama į kopėčias."""

    def test_the_device_said_in_passing_is_read(self, diagnosing):
        c = walk(
            diagnosing("healthy_to_router"),
            ["Gerai", "Neturiu, aš tik telefoną naudoju"],
        )
        assert c.state.case.facts["fail_scope"] == "single"
        assert c.state.case.facts["fail_device"] == "phone"
        assert c.rule == "case.wifi_ready" and not c.state.ticket.stage

    def test_a_working_device_is_not_the_failing_one(self):
        from agent.perceive.in_passing import failing_part

        assert "kompiuter" not in failing_part("Kompiuteryje veikia, telefone ne").lower()
        assert failing_part("Telefone neveikia internetas") == "Telefone neveikia internetas"

    def test_no_answer_about_the_device_still_goes_to_the_ladder(self, diagnosing):
        c = walk(
            diagnosing("healthy_to_router"), ["Gerai", "Neturiu", "Aš neturiu", "Kitų įrenginių"]
        )
        assert c.state.case.facts.get("fail_device") == "other"
        assert c.rule == "case.wifi_ready" and not c.state.ticket.stage


def test_the_ticket_tells_the_technician_what_to_check(diagnosing):
    """Tiketas — užduotis meistrui: kas nepatikrinta telefonu ir ką tikrinti (2026-11-05)"""
    c = walk(diagnosing("healthy_to_router"), ["Gerai", "Neturiu", "Telefone", "Taip, galiu"])
    walk(c, ["Registruokite meistrą", "Taip, tinka", "Bet kada"])
    ticket_type, details = _ticket(c.state.ticket.ticket_id)
    assert ticket_type == "fault_technician"  # asked for — a technician, not a call-back
    assert "Meistrui patikrinti:" in details and "DHCP" in details
    assert "Telefonu nespėta patikrinti:" in details and "Wi-Fi įjungimas" in details
    assert "telefonu nebeliko" not in details


class TestTheNewTree:
    """Andrius (2026-11-05): įrenginys → jo kopėčios → kiti įrenginiai → routeris → tiketas."""

    def test_a_different_network_on_the_working_device_is_joined(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS])
        assert c.rule == "case.other_devices"
        walk(c, ["Kompiuteryje veikia", "Ne, kitas pavadinimas"])
        assert c.rule == "case.wifi_join_same"
        walk(c, ["Prisijungiau", "Taip, veikia"])
        assert c.rule == "case.resolved"
        assert c.state.case.cause == "pack.healthy_to_router.cause.wrong_network"

    def test_no_other_device_reboots_the_router_then_registers(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS])
        c.say("Neturiu kito")
        assert c.rule == "case.reach"
        walk(c, ["Taip, galiu", "Perkroviau routerį", "Ne, vis tiek ne", "Gerai"])
        assert "reboot" in c.state.case.worked
        # Everything was done together: a technician, not „a colleague calls back".
        assert c.rule == "ticket.phone_intro" and c.state.ticket.reason == "visi_veiksmai"
        assert c.replies[-1].startswith("Atlikome visus veiksmus")

    def test_a_finding_during_the_registration_goes_back_to_the_fix(self, diagnosing):
        """„Aš dabar patikrinau, Wi-Fi išjungtas" per kontaktus — atgal į sprendimą"""
        c = walk(diagnosing("healthy_to_router"), [*OTHERS_WORK_PHONE, *LADDER_FAILS])
        walk(c, ["Neturiu kito", "Taip, galiu", "Perkroviau routerį", "Ne, vis tiek ne", "Gerai"])
        assert c.state.ticket.stage == "phone"
        c.say("Aš dabar patikrinau, Wi-Fi išjungtas")
        assert c.rule == "case.wifi_enable" and not c.state.ticket.stage
        walk(c, ["Įjungiau", "Taip, veikia"])
        assert c.rule == "case.resolved" and not c.state.ticket.ticket_id

    def test_nowhere_working_said_up_front_goes_to_the_router(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), ["Gerai", "Visuose įrenginiuose neveikia"])
        assert c.state.case.facts["fail_scope"] == "all"
        assert c.state.case.awaiting == "rebooted"

    def test_how_at_the_readiness_step_goes_to_where_to_tap(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), ["Gerai", "Telefone", "Kaip tai padaryti?"])
        assert c.rule == "case.how_to_os"
        c.say("OnePlus")
        assert c.rule == "case.how_to" and not c.state.ticket.stage

    def test_now_is_ready(self):
        from agent.perceive.detectors import detect_ready

        assert detect_ready("Dabar.") == "yes"
        assert detect_ready("Ne dabar, esu darbe") == "no"


class TestHeardFacts:
    """2026-11-06 (eval S9): what the caller says is collected whenever they say it, kept, and
    given to the engine; the caller's own doubt is remembered, not used."""

    def test_the_next_answer_answers_the_readiness_question(self, diagnosing):
        """„Patikrinau, WiFi įjungtas" to „ar galite pasižiūrėti?" — no „ar teisingai?", no
        repeated Wi-Fi question; it is said back"""
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE[:-1])
        assert c.rule == "case.wifi_ready"
        c.say("Patikrinau, WiFi įjungtas")
        assert c.state.case.facts["wifi_on"] == "yes"
        assert c.state.case.facts["device_ready"] == "yes"
        assert c.rule not in ("case.confirm", "case.wifi_state", "case.wifi_ready")
        assert "Wi-Fi įjungtas" in c.replies[-1]

    def test_doubt_asks_to_look_then_takes_the_answer(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE)
        assert c.rule == "case.wifi_state"
        c.say("Lyg ir įjungtas")
        assert c.rule == "case.hedged" and "wifi_on" not in c.state.case.facts
        c.say("Taip, įjungtas")
        assert c.state.case.facts["wifi_on"] == "yes"

    def test_does_not_know_is_not_no(self, diagnosing):
        c = walk(diagnosing("healthy_to_router"), OTHERS_WORK_PHONE)
        c.say("Nežinau")
        assert "wifi_on" not in c.state.case.facts
