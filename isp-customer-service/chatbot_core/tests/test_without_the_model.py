"""Be modelio tada, kai modelis nieko nebeprideda (L1 + L2, 2026-10-05).

Andrius: *„noriu pagalvoti apie delsą, kas ją sumažintų, nes dar yra taip, kad laukiame atsakymo
1–2 sekundes… o tu dabar padaryk L1 ir L2."*

Išmatuota iš trijų gyvų skambučių (59 ėjimai): ASR 0,55 s, **skaitymas modeliu 1,56 s**, variklis
**2 ms**, **žodžiai modeliu 1,16 s**, pirmas garsas klientui 3,0 s. Tad taisom ne variklį:

* **L1** — kai klausimas UŽDARAS ir jo paties skaitytuvas sakinį perskaito, modelio nebešaukiam
  (variklyje žodynas ir taip buvo pirmas: `case_rule` — *„žodynas lieka pirmas, jis nemokamas ir
  tikslus"*). Buvo 2 greitieji skaitymai iš 53.
* **L2** — kai žingsnio sakinys jau PARAŠYTAS kataloge ar dokumente ir ėjimas neturi ką kita
  pasakyti, jis sakomas taip, kaip parašytas. Buvo 49 ėjimai iš 62 per modelį.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from agent.contract import cards as catalog
from agent.ledger import record_client, record_telemetry

from tests.test_facts import BASE


@pytest.fixture
def call(make_state, make_runtime, monkeypatch):
    # Klausimo variantai skaitymui (ir greitasis kelias) gyvai yra įjungti; testų numatytasis
    # „CLASSIFIER=off" yra deterministinis režimas be jų.
    monkeypatch.setenv("CLASSIFIER", "on")
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    state.intake.problem_type = "internet_down"
    return state, rt


def _at_module(call, fault: str, module: str, *, said: bool = True):
    """Pokalbis stovi ties TUO kortelės žingsniu, ir jo klausimas jau nuskambėjo."""
    state, rt = call
    record_telemetry(state, rt, {**BASE, "observed_mac": None})
    record_client(state, rt, "reachable", "yes")
    state.case.fault, state.case.solution = fault, 0
    steps = catalog.card(fault).solution[0].steps
    state.case.step = next(i for i, s in enumerate(steps) if s.module == module)
    state.case.step_said = state.case.step if said else -1
    state.case.delivered = state.case.step
    # Išvada klientui jau pasakyta — kitaip ji eitų su šiuo atsakymu ir žodžius vestų modelis.
    state.case.announced = [fault]
    return state, rt


def _heard(state, text: str):
    """Klientas ką tik kažką pasakė — tyla variklyje yra atskiras, kantresnis kelias."""
    from agent.perceive.detectors import detect_turn_intent

    state.dialog.turn_count += 1
    state.dialog.last_heard = text
    state.dialog.last_intent = detect_turn_intent(text)


def _read(state, rt, text: str):
    from agent.perceive.perception import read_turn

    state.dialog.last_heard = text
    return read_turn(state, rt, text)


class TestL1TheDictionaryAnswerNeedsNoModel:
    def test_a_closed_answer_is_read_without_the_model(self, call):
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand") as llm,
        ):
            read = _read(state, rt, "Nedega nė viena")
        assert llm.call_count == 0, "uždaram atsakymui modelis nebešaukiamas"
        assert read is not None and read.source == "fast_path"
        assert read.step["label"] == "no" and read.step["is_answer"] is True

    def test_the_acknowledgement_still_comes_along(self, call):
        """Patvirtinimo pusė sakinio iki šiol atėjo iš modelio — dabar iš pakuotės."""
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand"),
        ):
            read = _read(state, rt, "Nedega nė viena")
        assert read.understood and "nedega" in read.understood.lower()

    def test_a_question_back_still_goes_to_the_model(self, call):
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand", return_value=None) as llm,
        ):
            _read(state, rt, "O kuri iš tų lempučių?")
        assert llm.call_count == 1

    def test_a_caller_who_does_not_follow_still_goes_to_the_model(self, call):
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand", return_value=None) as llm,
        ):
            _read(state, rt, "Nesuprantu, ko jūs iš manęs norite")
        assert llm.call_count == 1

    def test_a_long_answer_still_goes_to_the_model(self, call):
        """Ilgam sakiniui modelis šaukiamas ne dėl atsakymo, o dėl to, kas pasakyta PAKELIUI."""
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand", return_value=None) as llm,
        ):
            _read(
                state,
                rt,
                "Nedega nė viena lemputė, bet aš dar turiu kompiuterį ir jį perkroviau vakar",
            )
        assert llm.call_count == 1

    def test_the_contact_dialogue_is_the_models_own(self, call):
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        state.ticket.stage = "hours"
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand", return_value=None) as llm,
        ):
            _read(state, rt, "Bet kada")
        assert llm.call_count == 1


class TestL2WrittenWordsGoOutAsWritten:
    """L2 kol kas IŠJUNGTAS gyvai (`scripted_step_words: 0`) — testai jį įjungia, kad kelias
    neužželtų, kol sprendžiam dėl patvirtinimo (žr. FIX_PLAN „Banga 9")."""

    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("SCRIPTED_STEP_WORDS", "1")

    def _plan(self, state, rt):
        from agent.decide.rules import case_rule

        return case_rule.plan(state, rt)

    def test_the_catalogue_sentence_is_spoken_as_written(self, call):
        state, rt = _at_module(call, "router_hung", "reboot", said=False)
        _heard(state, "Taip, galiu prieiti")
        plan = self._plan(state, rt)
        assert plan.say.kind == "phrase" and plan.say.written is True
        assert "maitinimo laidą" in plan.say.text
        assert "Pasakykite, kai padarysite." in plan.say.text
        # Žymė, kad žingsnis nuskambėjo, dedama TEN, kur atsakymas ištariamas — ne čia: planą
        # dar gali perimti identifikacija ar tiketas, ir tada šie žodžiai nenuskambės.
        assert state.case.step_said != state.case.step
        state.turn.plan = plan.model_dump(mode="json")
        from agent.execute.step import mark_case_step_said

        mark_case_step_said(state)
        assert state.case.step_said == state.case.step

    def test_a_repeat_request_repeats_the_same_words(self, call):
        state, rt = _at_module(call, "router_hung", "reboot")
        _heard(state, "Pakartokit, ką reikia man padaryti")
        plan = self._plan(state, rt)
        assert plan.say.kind == "phrase" and plan.say.written is True
        assert plan.say.text.startswith("Ištraukite maitinimo laidą")

    def test_the_narrator_keeps_the_turn_when_there_is_more_to_say(self, call):
        state, rt = _at_module(call, "router_hung", "reboot", said=False)
        _heard(state, "Taip, galiu prieiti")
        state.turn.directives.summary = {"padaryta": "perkrovėm routerį"}
        assert self._plan(state, rt).say.kind == "directive"

    def test_the_narrator_keeps_the_turn_when_the_caller_is_lost(self, call):
        from agent.perceive.detectors import INTENT_CONFUSED

        state, rt = _at_module(call, "router_hung", "reboot", said=False)
        _heard(state, "Taip, galiu prieiti")
        state.dialog.last_intent = INTENT_CONFUSED
        assert self._plan(state, rt).say.kind == "directive"

    def test_a_question_shaped_fact_label_is_never_read_back(self, call):
        """Gyvai per eval'ą: „Gerai — ar gali dabar prieiti prie įrenginio turite." Tokio
        patvirtinimo geriau nesakyti visai."""
        from agent.decide.rules.case_rule import _remember_what_we_heard

        state, rt = _at_module(call, "router_hung", "reboot")
        state.case.awaiting = "reachable"
        _remember_what_we_heard(state)
        assert state.turn.heard_said is None

    def test_a_statement_fact_label_is_read_back(self, call):
        from agent.decide.rules.case_rule import _remember_what_we_heard

        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        record_client(state, rt, "lights", "off")
        state.case.awaiting = "lights"
        _remember_what_we_heard(state)
        assert state.turn.heard_said and "nedega" in state.turn.heard_said.lower()
