"""Agentas kaip ASISTENTAS: kiek reikia, tiek ir ves (8 banga, 2026-10-05).

Andrius: *„skaičiuoti ėjimus neteisinga — vienam klientui routeriui perkrauti užtenka vieno
sakinio, kitam reikia dešimties klausimų, ir tai ne ciklas, o darbas… tikslas padaryti būtinus
veiksmus, diagnozuoti problemą ir asistuoti. Klausimas, kaip nepapulti į ciklą."*

Atsakymas: skaičiuojam ne ėjimus, o TUŠČIUS ėjimus — ir tyla turi savo, kantresnį kelią.
"""

from __future__ import annotations

import pytest
from agent.decide.rules import case_rule
from agent.ledger import record_client, record_telemetry

from tests.test_facts import BASE


@pytest.fixture
def call(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    return state, rt


def _at_the_lights(call):
    state, rt = call
    record_telemetry(state, rt, {**BASE, "observed_mac": None})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution = "no_mac_observed", 0
    from agent.contract import cards as catalog

    steps = catalog.card("no_mac_observed").solution[0].steps
    state.case.step = next(i for i, s in enumerate(steps) if s.module == "check_lights")
    state.case.step_said = state.case.step
    return state, rt


def _heard(state, text: str):
    state.dialog.turn_count += 1
    if state.dialog.last_heard:
        state.dialog.recent_heard = [state.dialog.last_heard, *state.dialog.recent_heard][:3]
    state.dialog.last_heard = text
    from agent.perceive.detectors import detect_turn_intent

    state.dialog.last_intent = detect_turn_intent(text)


class TestAWorkingCallerIsNeverCutOff:
    def test_a_caller_who_keeps_looking_is_led_as_long_as_it_takes(self, call):
        """Dešimt ėjimų, kiekviename kažkas nauja — ir nė vieno pasidavimo."""
        state, rt = _at_the_lights(call)
        looking = [
            "Tuoj, einu pasižiūrėti",
            "Čia yra dvi dėžutės, nežinau kuri",
            "Viena po televizoriumi, kita prie stalo",
            "O kuri iš jų yra routeris?",
            "Gerai, žiūriu į tą prie stalo",
            "Čia daug lempučių, tokios mažos",
            "Viena šviečia, kitos tamsios",
            "Ar reikia pasakyti spalvą?",
            "Žalia ir viena oranžinė",
            "Dar pažiūriu iš kitos pusės",
        ]
        rules = []
        for words in looking:
            _heard(state, words)
            plan = case_rule.plan(state, rt)
            rules.append(plan.rule if plan else None)

        assert state.case.stall == 0, "kiekvienas ėjimas ką nors pridėjo"
        assert "case.last_chance" not in rules, rules
        assert not any(r and r.startswith("ticket.") for r in rules), rules

    def test_an_empty_turn_is_the_one_that_counts(self, call):
        state, rt = _at_the_lights(call)

        _heard(state, "Nežinau")
        case_rule.plan(state, rt)
        assert state.case.stall == 1

        _heard(state, "Čia tokia balta dėžutė su antenomis")  # nauja informacija
        case_rule.plan(state, rt)
        assert state.case.stall == 0, "pridėjo — skaitliukas nulinasi"

    def test_a_question_back_is_cooperation_not_a_loop(self, call):
        state, rt = _at_the_lights(call)

        _heard(state, "O kaip atrodo ta lemputė, apie kurią klausiate?")
        case_rule.plan(state, rt)

        assert state.case.stall == 0


class TestSilenceIsNotAnEmptyTurn:
    def test_silence_gets_its_own_patience(self, call):
        state, rt = _at_the_lights(call)
        state.dialog.turn_count += 1
        state.dialog.last_heard = ""

        case_rule.plan(state, rt)

        assert state.case.silence_asks == 1
        assert state.case.stall == 0, "tyla nėra tuščias ėjimas"

    def test_words_after_silence_clear_it(self, call):
        state, rt = _at_the_lights(call)
        state.dialog.last_heard = ""
        case_rule.plan(state, rt)
        _heard(state, "Atsiprašau, ieškojau to routerio")

        case_rule.plan(state, rt)

        assert state.case.silence_asks == 0


class TestOneMoreChanceBeforeTheTechnician:
    def test_the_last_chance_comes_first(self, call):
        state, rt = _at_the_lights(call)
        for _ in range(2):
            _heard(state, "Nežinau")
            plan = case_rule.plan(state, rt)

        assert plan.rule == "case.last_chance"
        told = state.turn.directives.last_chance
        assert told is not None and told["kas"], "pasakom, ko nepavyksta išsiaiškinti"

    def test_and_it_is_offered_once_per_step(self, call):
        state, rt = _at_the_lights(call)
        rules = []
        for _ in range(4):
            _heard(state, "Nežinau")
            plan = case_rule.plan(state, rt)
            rules.append(plan.rule if plan else None)

        assert rules.count("case.last_chance") == 1, rules

    def test_a_contribution_after_it_puts_the_work_back_on(self, call):
        state, rt = _at_the_lights(call)
        for _ in range(2):
            _heard(state, "Nežinau")
            case_rule.plan(state, rt)
        _heard(state, "A, radau — čia dega viena žalia lemputė")

        plan = case_rule.plan(state, rt)

        assert state.case.stall == 0
        assert plan is None or not plan.rule.startswith("ticket."), plan


class TestTheDocumentWaitsForTheCaller:
    """Gyvai 2026-10-05 (DHCP vedimas): modelis kiekvieną ėjimą teisingai sakė „waiting", o
    variklis dokumentą vis tiek judino — tad agentas prašė „Išsaugoti", kai klientas dar vedė
    admin/admin, ir „Internet/WAN", kai jis tik ėjo pažiūrėti lipduko."""

    def _walking(self, call):
        state, rt = call
        record_telemetry(state, rt, {**BASE, "dhcp_status": "no_requests", "traffic": "flowing"})
        record_client(state, rt, "panel_device", "yes")
        record_client(state, rt, "guide_agreed", "yes")
        from agent.contract import cards as catalog

        steps = catalog.card("dhcp_silent").solution[0].steps
        state.case.fault, state.case.solution = "dhcp_silent", 0
        state.case.step = next(i for i, s in enumerate(steps) if s.module == "guide")
        state.case.step_said = state.case.step
        state.case.guide_said = state.case.guide_step
        return state, rt

    def test_going_to_look_does_not_move_the_point(self, call):
        state, rt = self._walking(call)
        at = state.case.guide_step
        _heard(state, "Gerai, tuoj pažiūrėsiu ant lipduko, kur ten parašyta")
        state.turn.perception = {
            "step": {"label": "waiting", "is_answer": False, "confidence": 0.8}
        }

        case_rule.plan(state, rt)

        assert state.case.guide_step == at, "klientas dar tik eina žiūrėti"

    def test_a_question_mid_point_does_not_move_it(self, call):
        state, rt = self._walking(call)
        at = state.case.guide_step
        _heard(state, "Matau admin, admin sakot įvesti, ne?")
        state.turn.perception = {"step": {"label": "waiting", "is_answer": True, "confidence": 0.9}}

        case_rule.plan(state, rt)

        assert state.case.guide_step == at

    def test_a_real_report_moves_it(self, call):
        state, rt = self._walking(call)
        at = state.case.guide_step
        _heard(state, "Įvedžiau, esu viduje")
        state.turn.perception = {"step": {"label": "done", "is_answer": True, "confidence": 1.0}}

        case_rule.plan(state, rt)

        assert state.case.guide_step == at + 1
