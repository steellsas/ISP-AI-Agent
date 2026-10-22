"""6b (2026-10-15): a turn the engine's own reader already read does not call the model."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from agent.contract import cards as catalog
from agent.ledger import record_client, record_telemetry

from tests.diagnosis.test_facts import BASE

FUNCTION = "Skaitymas be modelio"


def _state(make_state):
    state = make_state("+37060012353")
    state.dialog.last_heard = "x"
    return state


@pytest.mark.parametrize(
    ("stage", "said", "value"),
    [
        ("phone", "Taip, tinka", "same_number"),
        ("phone", "Tiks", "same_number"),
        ("phone", "860012345", "860012345"),
        ("hours", "Bet kada", "Bet kada"),
        ("hours", "Nuo 17 iki 18", "Nuo 17 iki 18"),
    ],
)
def test_the_contact_answer_is_read_by_the_ticket_readers(make_state, stage, said, value):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    state.ticket.stage = stage
    read = fast_read(state, said, None)
    assert read is not None and read.source == "engine"
    assert read.ticket == {"type": "answer", "value": value}


@pytest.mark.parametrize("said", ["Ne, ne šis", "Netinka", "Velma", "O kada atvyks?"])
def test_what_the_reader_cannot_read_goes_to_the_model(make_state, said):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    state.ticket.stage = "phone"
    assert fast_read(state, said, None) is None


def test_the_problem_named_in_the_greeting(make_state):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    read = fast_read(state, "Labas, neveikia internetas", None)
    assert read is not None and read.problem == {"label": "internet_down", "confidence": 1.0}
    assert fast_read(state, "Sveiki", None) is None  # nothing named — the model reads it


def test_identification_turns_are_the_ladders(make_state):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    state.intake.problem_type = "internet_down"
    state.identity.customer_id = "CUST009"
    state.identity.result_pending = True
    assert fast_read(state, "Petras, nuomininkas", None).source == "engine"
    assert fast_read(state, "O kiek tai kainuos?", None) is None  # a question — the model


@pytest.mark.parametrize(
    ("said", "engine"),
    [("Aišku, ačiū", True), ("Ačiū, viso gero", True), ("Ačiū, bet TV irgi neveikia", False)],
)
def test_thanks_at_the_end(make_state, said, engine):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    state.intake.problem_type = "internet_down"
    state.identity.customer_id = "CUST009"
    state.closing.case_closed = True
    read = fast_read(state, said, None)
    assert (read is not None and read.source == "engine") is engine


def test_a_long_sentence_is_the_models(make_state):
    from agent.perceive.perception import fast_read

    state = _state(make_state)
    assert (
        fast_read(state, "Labas, neveikia internetas jau nuo vakar vakaro, kai grįžau", None)
        is None
    )


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


def _read(state, rt, text: str):
    from agent.perceive.perception import read_turn

    state.dialog.last_heard = text
    return read_turn(state, rt, text)


# --- from test_without_the_model.py ---


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

    @pytest.mark.parametrize(("said", "calls"), [("Bet kada", 0), ("Velma", 1)])
    def test_the_contact_dialogue_reads_what_its_readers_read(self, call, said, calls):
        """6b (2026-10-15): „Bet kada" is read by the hours reader — the model was even worse
        on it („other"); what the reader cannot read still goes to the model."""
        state, rt = _at_module(call, "no_mac_observed", "check_lights")
        state.ticket.stage = "hours"
        with (
            patch("agent.perceive.understand.enabled", return_value=True),
            patch("agent.perceive.understand.understand", return_value=None) as llm,
        ):
            _read(state, rt, said)
        assert llm.call_count == calls
