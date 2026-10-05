"""Ką klientas išgirsta pokalbio GALE (7c banga, gyvas skambutis 2026-10-02).

Andrius: *„prieš gedimo registravimą turi būti išvada: patikrinome routerį, lemputės nedega,
maitinimas ateina, laikinai prijungėme kitą įrenginį — internetas laikinai veiks, kol
nepakeisime routerio. Pasakyti, ką padarėme ir kodėl registruojame tiketą. Tas pats ir kai
nepavyksta išspręsti: padarėme tai ir tai, to nepavyko patikrinti. Klientas atsimins galutinį
pokalbį — ką agentas padėjo ir ko nepadarė."*

Tame pačiame skambutyje išlindo ir tai, kad po pririšimo klientas apie SĖKMĘ neišgirdo nė
žodžio — patikra užsidarė tylėdama, nes telemetrija jau rodė srautą.
"""

from __future__ import annotations

import pytest
from agent.contract import cards as catalog
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry

from tests.test_facts import BASE

# Linijoje jokio įrenginio: faktą `device_seen` gamina signalas `observed_mac`, tad būtent jį ir
# išimam (signals.yaml).
DEAD = {**BASE, "observed_mac": None}
# Tiltas pavyko: įrenginys matomas, MAC toks pat, srautas vaikšto.
BRIDGED = {**BASE, "traffic": "flowing"}


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060012353"), make_runtime()
    state.identity.customer_id = "CUST009"
    return state, rt


def _step_of(fault: str, module: str) -> int:
    steps = catalog.card(fault).solution[0].steps
    return next(i for i, call in enumerate(steps) if call.module == module)


def _dead_router_at(call, module: str, **facts):
    state, rt = call
    record_telemetry(state, rt, DEAD)
    record_client(state, rt, "reachable", "yes")
    record_client(state, rt, "lights", "off")
    record_client(state, rt, "power_cable", "plugged")
    for key, value in facts.items():
        record_client(state, rt, key, value)
    state.case.fault, state.case.solution = "no_mac_observed", 0
    state.case.step = _step_of("no_mac_observed", module)
    return state, rt


class TestTheBridgeSuccessIsToldBeforeAnythingElse:
    """Gyvai: po `update_mac` + `reset_port` telemetrija jau rodė įrenginį ir srautą, patikra
    užsidarė tylėdama, ir tą patį ėjimą kortelė nuėjo į eskalaciją."""

    def _after_the_bind(self, call):
        state, rt = _dead_router_at(call, "verify", has_computer="yes", bridge_agreed="yes")
        record_telemetry(state, rt, BRIDGED)
        # `worked` — kas tikrai vyko (iš jo išvada ir tiketas); `did` — kas pereita (`only_after`)
        state.case.worked = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        state.case.did = list(state.case.worked)
        return state, rt

    def test_the_line_proof_is_spoken_and_the_caller_is_asked(self, call):
        state, rt = self._after_the_bind(call)

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.verify"
        assert plan.action.type == "none", "zondas jau atsakė — šis ėjimas tik pasako ir klausia"
        proof = state.turn.directives.proof
        assert proof and proof["faktai"], "klientas turi išgirsti, ką linija rodo"
        assert plan.awaiting == "restored"

    def test_only_the_callers_own_answer_closes_the_step(self, call):
        state, rt = self._after_the_bind(call)
        at = state.case.step
        case_rule.plan(state, rt)

        assert state.case.step == at, "žingsnis nebaigtas, kol klientas neatsakė"

        state.case.step_said = state.case.step
        state.dialog.turn_count += 1
        record_client(state, rt, "restored", "yes")

        case_rule.plan(state, rt)

        assert state.case.step > at


class TestTheSummaryBeforeRegistering:
    def _at_the_end(self, call, **facts):
        state, rt = _dead_router_at(call, "escalate", **facts)
        # `worked` — kas tikrai vyko (iš jo išvada ir tiketas); `did` — kas pereita (`only_after`)
        state.case.worked = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        state.case.did = list(state.case.worked)
        return state, rt

    def test_it_says_what_was_done_and_why_before_the_ticket(self, call):
        state, rt = self._at_the_end(call, has_computer="yes", bridge_agreed="yes")
        record_telemetry(state, rt, BRIDGED)

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.summary"
        assert state.ticket.stage != "phone", "tiketo dialogas pradedamas TIK po išvados"
        told = state.turn.directives.summary
        assert told["padaryta"], "kas padaryta"
        assert "lemput" in told["padaryta"] and "elektra" in told["padaryta"]
        assert told["dabar"], "laikinas internetas PALEISTAS — tai pasakoma"
        assert told["kodel"], "kodėl registruojam"

    def test_then_the_ticket_dialogue_starts(self, call):
        state, rt = self._at_the_end(call, has_computer="yes", bridge_agreed="yes")

        first = case_rule.plan(state, rt)
        second = case_rule.plan(state, rt)

        assert first.rule == "case.summary"
        assert second.rule == "case.escalate" and state.ticket.stage == "phone"

    def test_a_refusal_is_in_the_summary_without_blame(self, call):
        """*„jei gedimo negalėjo išspręsti dėl kliento atsisakymo, tai irgi turi būti pasakyta."*"""
        state, rt = self._at_the_end(call, has_computer="yes", bridge_agreed="no")

        case_rule.plan(state, rt)

        told = state.turn.directives.summary
        assert told and "nenorėjot" in told["nepavyko"]

    def test_a_live_bridge_is_marked_so_the_ticket_knows(self, call):
        state, rt = self._at_the_end(call, has_computer="yes", bridge_agreed="yes")
        record_telemetry(state, rt, BRIDGED)

        case_rule.plan(state, rt)

        assert state.resolution.bridge_bound is True

    def test_after_the_summary_the_call_never_turns_into_solved(self, call):
        """Po išvados žingsnių nebelieka, ir be sargo variklis tai skaitė kaip „išspręsta" —
        agentas būtų pasakęs, kad internetas veikia."""
        state, rt = self._at_the_end(call, has_computer="yes", bridge_agreed="no")
        rules = []
        for _ in range(3):
            plan = case_rule.plan(state, rt)
            rules.append(plan.rule if plan else None)

        assert rules[0] == "case.summary"
        assert "case.resolved" not in rules, rules

    def test_nothing_was_done_means_no_summary(self, call):
        """Niekas nebuvo padaryta ir nieko neatsisakyta — nėra ko sumuoti, ir papildomo ėjimo
        klientas negauna."""
        state, rt = call
        record_telemetry(state, rt, DEAD)
        state.case.fault, state.case.solution = "no_mac_observed", 0

        assert case_rule._summary_words(state, catalog.card("no_mac_observed"), {}) is None


class TestTheFindingDoesNotTalkAboutNodes:
    """Andrius (2026-10-02): *„nereikia sakyti apie mazgus ir switch — tiesiog, kad iki jūsų
    ateina, bet nematome routerio ar kito įrenginio."*"""

    def test_the_provider_side_is_one_plain_sentence(self, call):
        state, rt = call
        record_telemetry(state, rt, DEAD)

        case_rule.plan(state, rt)

        told = state.case.finding
        assert told and "iki jūsų" in told["faktai"]
        assert "mazgas" not in told["faktai"] and "switch" not in told["faktai"].lower()
        assert "nematome" in told["faktai"]


class TestTheTechnicianGetsTheSameSummary:
    """Andrius (2026-10-02): *„apibendrinimas po skambučio bus reikalingas — pateikti meistrui,
    kas buvo ir kas buvo padaryta, tuomet tiketai bus informatyvūs."*

    Vienas šaltinis, du adresatai: klientui balsu, meistrui tikete.
    """

    def test_the_summary_survives_being_spoken(self, call):
        from agent.speak.context_card import _summary_to_tell

        state, rt = _dead_router_at(call, "escalate", has_computer="yes", bridge_agreed="yes")
        # `worked` — kas tikrai vyko (iš jo išvada ir tiketas); `did` — kas pereita (`only_after`)
        state.case.worked = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        state.case.did = list(state.case.worked)
        record_telemetry(state, rt, BRIDGED)
        case_rule.plan(state, rt)

        said = _summary_to_tell(state)

        assert said, "klientas išgirsta"
        assert state.case.summary_said is True
        assert _summary_to_tell(state) == [] or state.turn.directives.summary, "tik vieną kartą"
        assert state.case.summary["padaryta"], "duomenys LIEKA — jų reikia tiketui"

    def test_the_ticket_text_says_what_was_done(self, call):
        from agent.contract.locale import phrase

        state, rt = _dead_router_at(call, "escalate", has_computer="yes", bridge_agreed="yes")
        # `worked` — kas tikrai vyko (iš jo išvada ir tiketas); `did` — kas pereita (`only_after`)
        state.case.worked = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        state.case.did = list(state.case.worked)
        record_telemetry(state, rt, BRIDGED)
        case_rule.plan(state, rt)

        told = state.case.summary
        line = phrase("ticket.details.done", works=told["padaryta"])

        assert "Padaryta telefonu" in line and "lemput" in line
        assert "PALEISTAS" in phrase("ticket.details.bridge_live")


class TestTheSequenceIsNotSkippedOnAGuess:
    """Banga 7d, gyvas skambutis 2026-10-02 (antras mirusio routerio).

    Andrius: *„kai išgalvojami pasakymai ar veiksmai ir kai peršokama per seką — nepaklausiama,
    neišsiaiškinama iki galo."* Trys atskiri sargai, visi bendri, ne vienos kortelės.
    """

    def test_a_volunteered_guess_does_not_skip_a_confirming_question(self, call):
        """Gyvai: iš „dėžutė visiškai atrodo kaip be maitinimų" modelis padarė
        `power_cable=unplugged`, ir maitinimo klausimas buvo praleistas kaip „jau žinomas"."""
        state, rt = call
        record_telemetry(state, rt, DEAD)
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "unplugged")  # pasakyta pakeliui, ne atsakant
        state.case.fault, state.case.solution = "no_mac_observed", 0
        state.case.step = _step_of("no_mac_observed", "check_power")

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.check_power", "hipotezę patvirtinantis klausimas užduodamas"
        assert state.turn.directives.recheck, "ir užduodamas PATIKSLINANT, ne tuščiai"

    def test_a_done_word_cannot_settle_a_question_nobody_asked(self, call):
        """Gyvai: „Gerai, to patikrinsiu…" buvo atsakymas naratoriaus improvizuotam klausimui, o
        variklis tai užrašė kaip sutikimą su tiltu (`bridge_agreed=yes`)."""
        state, rt = call
        record_telemetry(state, rt, DEAD)
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "plugged")
        state.case.fault, state.case.solution = "no_mac_observed", 0
        state.case.step = _step_of("no_mac_observed", "offer_bridge")
        state.case.awaiting = "bridge_agreed"
        state.case.step_said = -1  # pasiūlymas NENUSKAMBĖJO
        state.dialog.turn_count += 1
        state.dialog.last_heard = "Gerai, tai patikrinsiu."

        case_rule.plan(state, rt)

        assert state.case.facts.get("bridge_agreed") is None

    def test_no_computer_stops_the_bridge_wherever_it_arrives(self, call):
        """Gyvai: „neturiu kompiuterio" atėjo jau PO pasiūlymo, tad `answered_when` nebeveikė, ir
        agentas tris kartus prašė kišti laidą į kompiuterį, kurio nėra."""
        state, rt = call
        record_telemetry(state, rt, DEAD)
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "plugged")
        record_client(state, rt, "bridge_agreed", "yes")  # „sutikimas" jau užrašytas
        state.case.fault, state.case.solution = "no_mac_observed", 0
        state.case.step = _step_of("no_mac_observed", "connect_direct")
        record_client(state, rt, "has_computer", "no")  # ir tik dabar paaiškėja

        plan = case_rule.plan(state, rt)

        assert plan.rule not in ("case.connect_direct", "case.bind", "case.port_reset")
        assert plan.rule in ("case.summary", "case.escalate")


class TestAFactWithoutAQuoteIsNotAFact:
    """Banga 7d: `ground()` atmesdavo faktą, kurio citatos nėra sakinyje, bet faktą BE citatos
    praleisdavo — ir būtent taip į „Džiugiu, Girino." atsirado `has_computer=no`."""

    def test_a_quoteless_fact_is_dropped(self):
        from agent.perceive.perception import Fact, Perception, ground

        read = Perception(facts={"has_computer": Fact(value="no")})

        grounded = ground(read, "Džiugiu, Girino.")

        assert grounded.facts["has_computer"].grounded is False

    def test_a_quoted_fact_that_was_really_said_stays(self):
        from agent.perceive.perception import Fact, Perception, ground

        read = Perception(facts={"lights": Fact(value="off", quote="nedega")})

        grounded = ground(read, "Nedega nė viena lemputė.")

        assert grounded.facts["lights"].grounded is True


class TestWhatWeClaimWeDid:
    """Banga 7e, gyvi skambučiai 2026-10-02 (13:57 ir 14:01).

    Du radiniai, abu apie SĄŽININGĄ buhalteriją — ne apie valdymą: tiketas rašė darbus, kurių
    nebuvo, o išvada po tilto kartojo pasenusią kortelės išvadą.
    """

    def _no_computer_at_the_end(self, call):
        state, rt = call
        record_telemetry(state, rt, DEAD)
        record_client(state, rt, "reachable", "yes")
        record_client(state, rt, "lights", "off")
        record_client(state, rt, "power_cable", "plugged")
        state.case.fault, state.case.solution = "no_mac_observed", 0
        state.case.step = _step_of("no_mac_observed", "offer_bridge")
        state.case.step_said = state.case.step
        record_client(state, rt, "has_computer", "no")
        record_client(state, rt, "bridge_agreed", "no")
        # lemputės ir maitinimas šiame skambutyje tikrai buvo eiti (fixture'as faktus suseda iš
        # karto, tad darbų sąrašą pažymim rankomis — testo dalykas yra tilto žingsniai)
        state.case.worked = ["check_lights", "check_power"]
        state.case.did = list(state.case.worked)
        return state, rt

    def test_a_skipped_step_is_not_a_job_we_did(self, call):
        """Gyvai: kompiuterio nebuvo, tiltas praleistas — o tikete rašė „prijungėm kompiuterį,
        pririšom, perkrovėm prievadą"."""
        state, rt = self._no_computer_at_the_end(call)

        for _ in range(3):
            case_rule.plan(state, rt)

        assert "connect_direct" in state.case.did, "`only_after` turi matyti, kad žingsnis pereitas"
        assert "connect_direct" not in state.case.worked
        told = state.case.summary or {}
        assert "prijungėm kompiuterį" not in told.get("padaryta", "")
        assert "lemput" in told.get("padaryta", ""), "o tai, kas tikrai vyko, pasakoma"

    def test_no_computer_is_not_a_refusal(self, call):
        state, rt = self._no_computer_at_the_end(call)

        for _ in range(3):
            case_rule.plan(state, rt)

        told = state.case.summary or {}
        assert "nebuvo kuo" in told.get("nepavyko", "")
        assert "nenorėjot" not in told.get("nepavyko", "")

    def test_after_a_live_bridge_the_stale_conclusion_is_dropped(self, call):
        """Gyvai: „pririšome jį tiesiai prie linijos. Linijoje jūsų routeris nematomas" — o
        telemetrija tuo metu rodė `device_seen=yes, device_registered=match`."""
        state, rt = _dead_router_at(call, "escalate", has_computer="yes", bridge_agreed="yes")
        state.case.worked = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        state.case.did = list(state.case.worked)
        record_telemetry(state, rt, BRIDGED)

        case_rule.plan(state, rt)

        told = state.case.summary
        assert told["dabar"], "pasakom, kas veikia dabar"
        assert "nematome" not in told["isvada"], "pasenusi išvada nebekartojama"
        assert told["kodel"], "o kodėl reikia meistro — pasakoma"


class TestAQuestionDoesNotDerailTheFix:
    """Banga 7e: į „laukiu, sakykit kada" naratorius atsakė *„deja, negaliu patarti, kaip tai
    padaryti"* — kaip tik tada, kai pririšimas buvo sėkmingas."""

    def test_the_step_words_ride_with_the_answer(self, call):
        from agent.speak.context_card import _question_mid_fix

        state, rt = _dead_router_at(call, "check_lights")
        state.turn.plan = {"rule": "dialog.question_passthrough"}

        said = _question_mid_fix(state)

        assert said, "sprendimo viduryje klausimas atsakomas IR žingsnis tęsiamas"
        assert "lemput" in said[0].lower(), "su kortelės žodžiais"
        assert "cannot advise" in said[0], "ir su aiškiu uždraudimu dėl žinių ribos"
        assert state.case.step_said == state.case.step, "klausimas nuskambėjo — vadinasi, pažymėtas"

    def test_outside_a_fix_it_says_nothing(self, call):
        from agent.speak.context_card import _question_mid_fix

        state, rt = call
        state.turn.plan = {"rule": "dialog.question_passthrough"}

        assert _question_mid_fix(state) == []


class TestALostCallerIsNotAnIdentificationProblem:
    """Banga 7f, gyvas DHCP skambutis 2026-10-02.

    Andrius: *„kaip ir būtų suveikę gerai, tik užbaigė — neaišku, ko jis neišgirdo… ir kai kada
    kartojo pasakymą kelis kartus; vienas buvo, kad paprašiau pakartoti."*

    Trace: trys beveik vienodi vedimo punktai (vieno pakartoti paprašė pats klientas) pakėlė
    `stuck_count` iki 3, ir agentas pasakė *„Atsiprašau, vis nepavyksta išgirsti. Gal turite
    abonento kodą nuo sąskaitos?"* — identifikacijos taktiką identifikuotam klientui vedimo
    viduryje — o paskui užregistravo gedimą ir atsisveikino.
    """

    def test_a_requested_repeat_is_not_a_loop(self):
        from agent.dialog_utils import progress_key
        from agent.speak.postprocess import track_stuck

        from tests.calls import make_agent

        a = make_agent("+37060020106", language="lt")
        step = "Dabar paspauskite „Išsaugoti (Save / Apply)“."
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, step)

        a.state.dialog.last_heard = "Pakartokit, ką reikia man padaryti."
        a.state.turn.progress_key_at_start = progress_key(a.state)
        track_stuck(a.state, a.runtime, step)

        assert a.state.dialog.stuck_count == 0, "klientas pats paprašė pakartoti"

    def test_walking_the_document_counts_as_progress(self):
        """Gyvai: kiekvienas vedimo punktas judėjo pirmyn, bet `progress_key` to nematė — tad tą
        patį punktą perfrazavus skaitliukas kilo, ir po trijų suveikė identifikacijos kopėčia."""
        from agent.dialog_utils import progress_key

        from tests.calls import make_agent

        a = make_agent("+37060020106", language="lt")
        a.state.case.fault, a.state.case.solution = "dhcp_silent", 0
        before = progress_key(a.state)
        a.state.case.guide_step += 1

        assert progress_key(a.state) != before

    def test_the_account_code_ladder_stays_out_of_a_fix(self, call):
        from agent.decide.rules.dialog import stuck_backstop

        state, rt = call
        state.case.fault, state.case.solution = "dhcp_silent", 0
        state.dialog.stuck_count = 3

        assert stuck_backstop(state) is None

    def test_the_fix_ends_with_a_summary_instead(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests", "traffic": "flowing"})
        record_client(state, rt, "panel_device", "yes")
        record_client(state, rt, "guide_agreed", "yes")
        state.case.fault, state.case.solution = "dhcp_silent", 0
        state.case.step = _step_of("dhcp_silent", "guide")
        state.case.worked = ["guide"]
        state.case.did = ["guide"]
        state.dialog.stuck_count = 3
        state.case.stall = 2  # ir tušti ėjimai: klientas nebepriduria nieko (8 banga)

        plan = case_rule.plan(state, rt)

        assert plan.rule == "case.summary"
        told = state.turn.directives.summary
        assert "pabaigti nepavyko" in told["nepavyko"]
