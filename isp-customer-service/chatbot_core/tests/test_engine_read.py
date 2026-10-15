"""6b (2026-10-15): a turn the engine's own reader already read does not call the model."""

import pytest


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
