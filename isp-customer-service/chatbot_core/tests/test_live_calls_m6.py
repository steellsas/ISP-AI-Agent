"""The owner's M6 live calls (2026-09-17): each failure kept as a regression test."""

import json


def _identified(make_state, phone="+37060030307", customer="CUST307"):
    state = make_state(phone)
    state.identity.customer_id = customer
    return state


class TestBackgroundReadKeepsEngineVerdicts:
    """A — a repeat call's open-ticket verdict was overwritten by the background read
    (node fault) and a duplicate ticket was registered."""

    def test_a_verdict_decided_without_telemetry_is_kept(self, make_state, make_runtime):
        from agent.background import apply_bg_diagnosis

        state = _identified(make_state)
        state.diagnosis.verdicts["network"] = {"reason": "open_ticket_exists", "skipped": True}
        state.turn.bg_diagnosis = json.dumps({"verdict": {"reason": "node_fault_unregistered"}})

        apply_bg_diagnosis(state, make_runtime())

        assert state.diagnosis.verdicts["network"]["reason"] == "open_ticket_exists"


class TestHolderClarifyIsNotTheResult:
    """B — the holder-name question counted as the delivered news; the outage ETA and the
    debt template never went out."""

    def test_the_result_stays_pending_through_the_clarify(self, make_state, make_runtime):
        from agent.execute.step import mark_step_presented

        state = _identified(make_state, "+37060020102", "CUST102")
        state.identity.result_pending = True
        state.identity.caller_name = "Vilma"
        state.identity.holder_clarify_open = True
        state.identity.holder_clarify_asked = True

        mark_step_presented(state, make_runtime())

        assert state.identity.result_pending is True
        assert state.diagnosis.news_delivered is False


class TestStartedRequestIsNotDiagnosed:
    """C — a billing request became an unclear fault and the cancel-confirm spoke of a
    technician."""

    def test_no_second_diagnosis(self, make_state, make_runtime):
        from agent.decide.rules import requests
        from agent.execute.diagnosis import ensure_diagnosed

        state = _identified(make_state, "+37060020109", "CUST109")
        state.intake.problem_type = "billing"
        rt = make_runtime()
        requests.start_request(state, rt)

        ensure_diagnosed(state, rt)

        assert state.resolution.procedure is None
        assert state.ticket.request_type == "billing_request"

    def test_the_cancel_confirm_speaks_of_the_request(self, make_state, make_runtime):
        from agent.contract.locale import phrase

        text = phrase("identification.ticket_cancel_confirm_request")
        assert "meistr" not in text and "atsakingam" in text


class TestServiceNamedTogether:
    """D — „tvarkykit" matched the TV trigger; „internetas, televizija" became a TV fault."""

    def test_tvarkykit_is_not_tv(self):
        from agent.perceive.nlu import classify_problem

        assert (
            classify_problem("Labą dieną, neveikia internetas. Nežinau, tvarkykit jūs")
            == "internet_down"
        )

    def test_internet_and_tv_together_is_the_internet(self):
        from agent.perceive.nlu import classify_problem

        assert (
            classify_problem("Labas, neveikia internetas, televizija, niekas neveikia")
            == "internet_down"
        )

    def test_tv_alone_is_still_tv(self):
        from agent.perceive.nlu import classify_problem

        assert classify_problem("televizorius neveikia") == "tv"
        assert classify_problem("neberodo tv, kanalai dingo") == "tv"


class TestCallerName:
    """E — a refused name was re-asked, and a garbled one went on the record verbatim."""

    def _owed(self, make_state):
        state = _identified(make_state, "+37060020101", "CUST101")
        state.identity.result_pending = True
        return state

    def test_a_refused_name_is_not_re_asked(self, make_state, make_runtime):
        from agent.decide.rules.head import caller_intro

        state = self._owed(make_state)
        assert caller_intro(state, make_runtime(), "Nesvarbu, koks mano vardas. Sakyk, ką turiu.")
        assert state.identity.caller_name == "nenurodyta"

    def test_an_unreadable_name_is_not_the_sentence(self, make_state, make_runtime):
        from agent.decide.rules.head import caller_intro

        state = self._owed(make_state)
        caller_intro(state, make_runtime(), "po anas mano vardas.")
        assert state.identity.caller_name == "nenurodyta"
        assert state.identity.caller_name_heard is False
