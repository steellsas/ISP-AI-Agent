"""Requests (M6, D-11): a question outside the agent's knowledge is registered for the
responsible person — never answered, never diagnosed."""

from agent.decide.rules import requests
from agent.decide.rules.ticket import caller_owed


def _caller(make_state, problem, said):
    state = make_state("+37060020109")
    state.identity.customer_id = "CUST109"
    state.intake.problem_type = problem
    state.intake.heard_utterances = [said, "Taip", "Aldona"]
    return state


class TestStartRequest:
    def test_a_billing_question_starts_a_billing_request(self, make_state, make_runtime):
        state = _caller(make_state, "billing", "kodėl tokia didelė sąskaita")

        requests.start_request(state, make_runtime())

        assert state.ticket.request_type == "billing_request"
        assert state.ticket.stage == "phone"
        assert state.resolution.procedure is None  # nothing diagnosed

    def test_the_caller_name_comes_before_the_contacts(self, make_state, make_runtime):
        state = _caller(make_state, "billing", "kodėl tokia didelė sąskaita")
        state.identity.result_pending = True
        requests.start_request(state, make_runtime())

        assert caller_owed(state)
        state.identity.caller_name = "Aldona"
        assert not caller_owed(state)


class TestTicketStatus:
    def test_no_open_ticket_is_said_plainly(self, make_state, make_runtime):
        from agent.inform import inform_text

        state = _caller(make_state, "ticket_status", "kada atvažiuos meistras")
        rt = make_runtime()

        requests.answer_ticket_status(state, rt)

        assert state.diagnosis.verdicts["network"]["reason"] == "no_open_ticket"
        assert "nematau" in inform_text(state, rt, "no_open_ticket")

    def test_an_open_ticket_gets_the_note_and_its_status(self, make_state, make_runtime):
        calls = []
        state = _caller(make_state, "ticket_status", "kada atvažiuos meistras")
        state.identity.open_tickets = [
            {"ticket_id": "TKT9", "problem_type": "internet_down", "status": "open"}
        ]
        rt = make_runtime(fake_tools=lambda name, args: calls.append((name, args)) or {})

        requests.answer_ticket_status(state, rt)

        assert calls and calls[0][0] == "append_ticket_note" and calls[0][1]["ticket_id"] == "TKT9"
        assert state.closing.appended_ticket_id == "TKT9"


class TestDebtDispute:
    def _told_debt(self, make_state):
        state = _caller(make_state, "internet_down", "neveikia internetas")
        state.diagnosis.verdicts["network"] = {"reason": "billing_suspended"}
        state.diagnosis.news_delivered = True
        return state

    def test_a_dispute_gets_the_offer_and_a_yes_starts_a_billing_request(
        self, make_state, make_runtime
    ):
        state = self._told_debt(make_state)
        rt = make_runtime()

        assert requests.debt_offer_turn(state, rt, "Kaip tai skola, aš sumokėjau") == "ask"
        assert requests.debt_offer_turn(state, rt, "Taip, užregistruokite") == "start"
        assert state.ticket.request_type == "billing_request"
        assert state.ticket.request_note == "Kaip tai skola, aš sumokėjau"

    def test_agreeing_with_the_debt_is_no_dispute(self, make_state, make_runtime):
        state = self._told_debt(make_state)

        assert requests.debt_offer_turn(state, make_runtime(), "Aišku, ačiū, sumokėsiu") is None

    def test_a_declined_offer_registers_nothing(self, make_state, make_runtime):
        state = self._told_debt(make_state)
        rt = make_runtime()
        requests.debt_offer_turn(state, rt, "Nesutinku su ta skola")

        assert requests.debt_offer_turn(state, rt, "Ne, nereikia") is None
        assert state.ticket.request_type is None and state.ticket.stage is None


def test_a_request_ticket_is_about_its_own_intent():
    from agent.intents import intent_for_ticket_type

    assert intent_for_ticket_type("billing_request") == "billing"
    assert intent_for_ticket_type("fault_technician") is None
