"""Ticket rules (§5 row 3): the caller's answer at the contact dialogue -> the plan."""

from unittest.mock import patch

from agent.decide.rules import ticket
from agent.graph_v2.state import TicketContext, TicketState, TurnScratch


def _state(make_state, stage, text, **ctx):
    context = TicketContext(phone_asked=True, hours_asked=True, intro_done=True, **ctx)
    state = make_state(
        "+37060012353",
        ticket=TicketState(stage=stage, context=context),
        turn=TurnScratch(user_input=text),
    )
    state.identity.customer_id = "CUST009"
    return state


def _plan(make_state, make_runtime, stage, text, understood=None, **ctx):
    state = _state(make_state, stage, text, **ctx)
    with (
        patch("agent.perceive.understand.enabled", return_value=understood is not None),
        patch("agent.perceive.understand.understand_ticket", return_value=understood),
    ):
        return state, ticket.plan(state, make_runtime())


def test_phone_captured_then_hours_question(make_state, make_runtime, monkeypatch):
    monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
    state, plan = _plan(
        make_state, make_runtime, "phone", "tinka šis", {"value": "same_number", "type": "answer"}
    )
    assert state.ticket.stage == "hours" and state.ticket.contact_phone == "+37060012353"
    assert plan.rule == "ticket.ask_hours" and plan.say.kind == "directive"


def test_hours_captured_registers(make_state, make_runtime):
    state, plan = _plan(
        make_state, make_runtime, "hours", "po pietų", {"value": "po pietų", "type": "answer"}
    )
    assert plan.rule == "ticket.register" and plan.action.type == "register_ticket"


def test_unclear_phone_retries_once(make_state, make_runtime):
    _state_, plan = _plan(make_state, make_runtime, "phone", "hmm nežinau ką", None)
    assert plan.rule == "ticket.retry_phone" and plan.say.text


def test_offscript_question_goes_to_the_narrator(make_state, make_runtime):
    _state_, plan = _plan(
        make_state, make_runtime, "phone", "O kas skambins?", {"value": None, "type": "question"}
    )
    assert plan.rule == "ticket.offscript_question" and plan.say.kind == "directive"


def test_confirmed_refusal_cancels(make_state, make_runtime):
    from agent.execute.actions import run_action

    state, plan = _plan(make_state, make_runtime, "phone", "Ne.", None, cancel_confirm_out=True)
    assert plan.rule == "ticket.cancelled"
    assert plan.action.type == "close" and plan.action.name == "declined"

    run_action(state, make_runtime(), plan)
    assert state.closing.case_closed and state.closing.closed_reason == "declined"
    assert state.closing.is_complete is True


def test_no_dialogue_is_not_the_ticket_rules(make_state, make_runtime):
    state = make_state("+37060012353", turn=TurnScratch(user_input="taip"))
    assert ticket.plan(state, make_runtime()) is None


class TestTheHoursFieldKeepsOnlyTheTime:
    """Live 2026-09-23: "Galit meistrą registruoti. Nuo 12 iki 1" landed on the ticket whole
    and was read back to the caller."""

    def test_the_other_sentence_is_dropped(self):
        from agent.decide.rules.ticket import _hours_only

        assert _hours_only("Galit meistrą registruoti. Nuo 12 iki 1") == "Nuo 12 iki 1"
        assert _hours_only("Taip, tinka. Po 17 valandos.") == "Po 17 valandos"

    def test_a_single_thought_is_kept_whole(self):
        from agent.decide.rules.ticket import _hours_only

        assert _hours_only("Bet kada") == "Bet kada"
        assert _hours_only("Po pietų, nuo keturioliktos") == "Po pietų, nuo keturioliktos"

    def test_an_answer_with_no_time_at_all_is_not_emptied(self):
        from agent.decide.rules.ticket import _hours_only

        assert _hours_only("Nežinau. Nesuprantu.") == "Nežinau. Nesuprantu."
