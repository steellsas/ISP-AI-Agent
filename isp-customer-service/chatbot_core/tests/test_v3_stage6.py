"""v3 stage 6 (docs/review/PROMPTAI.md) — the prompt by phase and what measuring it uncovered."""

import pytest


@pytest.mark.parametrize(
    ("said", "statements"),
    [
        ("Gerai, ačiū, veikia. Alio, kada dėl routerio paskambinsit?", "Gerai, ačiū, veikia."),
        ("Ar veikia jūsų sistema?", ""),
        ("Veikia, ačiū", "Veikia, ačiū"),
    ],
)
def test_a_result_is_read_from_statements_not_questions(said, statements):
    from agent.decide.rules.stage import statements_only

    assert statements_only(said) == statements


class TestTheFixAnswerWithAQuestion:
    """Eval S4b under 6a: „Gerai, ačiū, veikia. Alio, kada dėl routerio paskambinsit?" at the
    bridge — the side topic froze the Case, „veikia" was lost, the model invented a step and
    the fault was never registered. (Before 6a it passed by luck: the model happened to say a
    prompt example „…užregistruosiu jūsų klausimą", and the promise guard registered it.)"""

    @pytest.fixture
    def bridging(self, make_state, make_runtime):
        state, rt = make_state("+37060012353"), make_runtime()
        state.identity.customer_id = "CUST009"
        state.case.fault, state.case.solution, state.case.step = "no_mac_observed", 0, 6
        state.turn.side_topic_active = True
        return state, rt

    def test_the_case_keeps_the_turn(self, bridging):
        from agent.decide.rules.stage import _carries_a_fix_answer

        state, _ = bridging
        state.dialog.last_heard = "Gerai, ačiū, veikia. Alio, kada dėl routerio paskambinsit?"
        assert _carries_a_fix_answer(state)

    def test_a_plain_side_question_still_is_one(self, bridging):
        from agent.decide.rules.stage import _carries_a_fix_answer

        state, _ = bridging
        state.dialog.last_heard = "O kiek kainuoja meistras?"
        assert not _carries_a_fix_answer(state)

    def test_said_it_works_is_not_asked_again(self, bridging):
        from agent.decide.rules.case_rule import _caller_says_it_works

        state, _ = bridging
        state.dialog.last_heard = "Gerai, ačiū, veikia. Alio, kada dėl routerio paskambinsit?"
        assert _caller_says_it_works(state)
        state.dialog.last_heard = "Ar jau veikia?"
        assert not _caller_says_it_works(state)


@pytest.mark.parametrize(
    ("said", "waits"),
    [
        ("Gerai", True),  # „ok, doing it" — not „done"
        ("Turiu kabelį rankoje", True),
        ("Patikrinau, WiFi įjungtas", False),  # their own words say it is done
    ],
)
def test_a_nod_or_work_in_hand_is_not_done(said, waits):
    from agent.perceive.detectors import detect_turn_intent, says_done_action

    in_progress = detect_turn_intent(said) == "in_progress"
    from agent.contract.locale import vocab

    nod = len(said.split()) <= 3 and any(m in said.lower() for m in vocab("acknowledge"))
    assert (nod or in_progress) is waits
    assert says_done_action(said) is (not waits)


@pytest.mark.parametrize("said", ["Ne, ačiu, viskas", "Ne, aciu, viskas", "Ne, ačiū, viskas"])
def test_a_goodbye_without_its_diacritics_is_a_goodbye(said):
    """Eval S1 under 6a: „Ne, ačiu, viskas" after „anything else?" reopened a solved call."""
    from agent.decide.rules.closing import _still_down
    from agent.perceive.detectors import detect_farewell

    assert detect_farewell(said)
    assert not _still_down(said)
