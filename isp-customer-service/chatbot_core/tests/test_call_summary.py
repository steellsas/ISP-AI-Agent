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
        state.case.did = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
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
        state.case.did = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
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
        state.case.did = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
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
        state.case.did = ["check_lights", "check_power", "connect_direct", "bind", "port_reset"]
        record_telemetry(state, rt, BRIDGED)
        case_rule.plan(state, rt)

        told = state.case.summary
        line = phrase("ticket.details.done", works=told["padaryta"])

        assert "Padaryta telefonu" in line and "lemput" in line
        assert "PALEISTAS" in phrase("ticket.details.bridge_live")
