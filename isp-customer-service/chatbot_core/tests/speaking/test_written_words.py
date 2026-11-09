"""Kalba — Rašyti žodžiai be modelio."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from agent.contract import cards as catalog
from agent.ledger import record_client, record_telemetry

from tests.diagnosis.test_facts import BASE

FUNCTION = "Rašyti žodžiai be modelio"


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


# --- from test_without_the_model.py ---


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
        # 2026-11-06: every caller fact has ONE prepared statement (`evidence.said_back`) —
        # never the question-shaped label glued to a value.
        assert state.turn.heard_said in (None, "galite prieiti prie įrenginio")

    def test_a_statement_fact_label_is_read_back(self, call):
        from agent.decide.rules.case_rule import _remember_what_we_heard

        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        record_client(state, rt, "lights", "off")
        state.case.awaiting = "lights"
        _remember_what_we_heard(state)
        assert state.turn.heard_said and "nedega" in state.turn.heard_said.lower()


class TestCaseStory:
    """2026-11-09: the speaker knows how the case went; only the engine registers."""

    def test_every_step_the_caller_does_has_a_reason(self):
        from agent.contract.locale import phrase_or

        needed = [
            "reboot",
            "cable_seated",
            "cable_reseat",
            "nic_enabled",
            "wifi_state",
            "check_power",
        ]
        assert [m for m in needed if not phrase_or(f"step_why.{m}", "")] == []

    def test_story_says_what_was_tried_and_ticket_state(self, call):
        from agent.speak.context_card import case_story

        state, rt = _at_module(call, "router_hung", "verify")
        state.case.worked = ["reboot"]
        state.case.facts["restored"] = "no"
        story = "\n".join(case_story(state, rt))
        assert "perkrovėme routerį" in story and "vis dar neveikia" in story
        assert "NOT registered" in story
        assert "restored" not in story

    def test_goal_is_shown_last(self, call):
        from agent.speak.context_card import context_card

        state, rt = _at_module(call, "router_hung", "reboot")
        state.turn.plan = {"rule": "case.reboot", "say": {"goal": "the reboot done"}}
        card = context_card(state, rt)
        assert card.index("THE CASE SO FAR") < card.index("THIS REPLY:") < card.index("PLAN GOAL")

    def test_failed_step_is_named_on_the_written_path(self, call):
        from types import SimpleNamespace

        from agent.decide.rules.case_rule import _did_not_help

        state, rt = _at_module(call, "router_hung", "verify")
        state.case.worked = ["cable_reseat", "verify"]
        state.case.facts["restored"] = "no"
        state.case.moved_on_turn = state.dialog.turn_count
        said = _did_not_help(state, SimpleNamespace(text="trumpas"))
        assert said.startswith("Įkišome laidą iš naujo, bet internetas vis dar neveikia.")
        state.case.moved_on_turn = state.dialog.turn_count - 1
        assert _did_not_help(state, SimpleNamespace(text="trumpas")) == ""
