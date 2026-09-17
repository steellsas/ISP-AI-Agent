"""The identification gate (M6, D-09): nothing about an account before it is confirmed."""

from agent.decide.rules.identification import release_held_outage
from agent.speak.context_card import context_card

HELD = {"customer_id": "CUST102", "street": "Tilžės g.", "eta": "18:00", "description": "x"}


class TestHeldOutage:
    def test_the_card_says_nothing_about_a_held_outage_before_confirmation(
        self, make_state, make_runtime
    ):
        state, rt = make_state("+37060020102"), make_runtime()
        state.intake.problem_type = "internet_down"
        state.identity.held_outage = dict(HELD)

        card = context_card(state, rt) or ""

        assert "OUTAGE" not in card and "Tilžės" not in card and "18:00" not in card

    def test_it_is_released_for_the_confirmed_candidate(self, make_state, make_runtime):
        state, rt = make_state("+37060020102"), make_runtime()
        state.identity.held_outage = dict(HELD)
        state.identity.customer_id = "CUST102"

        release_held_outage(state, rt)

        assert state.identity.held_outage == HELD

    def test_it_is_discarded_when_the_caller_is_another_customer(self, make_state, make_runtime):
        state, rt = make_state("+37060020102"), make_runtime()
        state.identity.held_outage = dict(HELD)
        state.identity.customer_id = "CUST009"  # they called about another address

        release_held_outage(state, rt)

        assert state.identity.held_outage is None

    def test_a_different_street_discards_it(self, make_state, make_runtime):
        from agent.perceive.slots import prefill_slots_from_text

        state, rt = make_state("+37060020102"), make_runtime()
        state.identity.held_outage = dict(HELD)

        prefill_slots_from_text(state, rt, "neveikia internetas Vilniaus gatvėje 29")

        assert state.identity.held_outage is None


class TestNoAccountTalkBeforeConfirmation:
    def test_the_address_offer_runs_even_with_a_held_outage(self, make_state, make_runtime):
        """Before M6 the ladder skipped the offer and asked about the outage's street."""
        from agent.decide.rules.identification import _address_move

        state, rt = make_state("+37060020102"), make_runtime()
        state.intake.problem_type = "internet_down"
        state.identity.phone_candidate = {
            "customer_id": "CUST102",
            "street": "Tilžės g.",
            "house": "60",
            "city": "Šiauliai",
            "address": "Tilžės g. 60, Šiauliai",
        }
        state.identity.held_outage = dict(HELD)

        reply = _address_move(state, rt, state)

        assert state.dialog.active_question.key == "address_offer"
        assert "Tilžės g. 60" in (reply or "")  # the offer, not a question about the outage
