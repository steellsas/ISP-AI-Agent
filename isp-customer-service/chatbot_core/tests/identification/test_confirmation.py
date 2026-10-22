"""Patvirtinimas — nothing about an account before the address is confirmed (M6, D-09): the held
outage, the line, the debt wait for the caller's „taip".
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.decide.rules.identification import release_held_outage
from agent.graph_v2.state import TicketContext
from agent.speak.context_card import context_card

from tests.tool_fakes import install_fake_tools

from .helpers import _agent

FUNCTION = "Patvirtinimas"


def test_a_dictated_address_waits_for_the_yes(call):
    """Padiktuotas adresas — tik po „taip“"""
    c = call()
    c.say("Neveikia internetas")
    c.say("Vilniaus gatvė 29")
    assert c.identity.customer_id is None and not c.identity.address_confirmed
    c.say("Taip")
    assert c.identity.customer_id == "CUST009" and c.identity.address_confirmed


def test_an_offered_address_waits_for_the_yes(call):
    """Pasiūlytas adresas — tik po „taip“"""
    c = call("+37060020112")
    c.say("Neveikia internetas")
    assert c.identity.customer_id is None
    reply = c.say("Taip")
    assert c.identity.customer_id == "CUST112" and "Vilniaus g. 33-2" in reply


# --- from test_identification_gate.py ---


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


# --- from test_agent.py ---


class TestAddressGuards:
    """Round-3 live bugs: a garbled reply must not commit the offered address, and a
    post-identification correction must reopen identification."""

    def test_garbled_taip_nebija_is_not_a_confirm(self):
        from agent.perceive.detectors import detect_address_confirm

        assert detect_address_confirm("Taip, nebija") is None  # mixed -> re-ask
        assert detect_address_confirm("Taip, tvirtinu") == "yes"
        assert detect_address_confirm("Ne, dėl kito adreso") == "no"
        # Problem words are not denials: "neveikia" alongside taip still confirms.
        assert detect_address_confirm("Taip, neveikia internetas dėl to adreso") == "yes"

    def test_pre_turn_guard_vetoes_commit(self, db_connection):
        from agent.decide.rules.head import turn_head
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.messages.append(
            {"role": "assistant", "content": "Ar skambinate dėl Tilžės g. 60, butas 3?"}
        )
        turn_head(agent.state, agent.runtime, "Taip, nebija")
        assert agent.state.turn.address_confirm_note is not None  # veto: do not resolve the offer
        facts = context_card(agent.state, agent.runtime)
        assert facts and "NEPATVIRTINTAS" in facts

    def test_correction_asks_confirmation_then_reopens(self, db_connection):
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        # Etalonas №3 (2026-09-03): a correction no longer reopens INSTANTLY —
        # one confirmation question first; a "taip" (or a named new address)
        # then drops the identity.
        from tests.calls import make_agent

        agent = make_agent("+37060020101")
        agent.state.identity.customer_id = "CUST101"
        agent.state.identity.customer_address = "Šiauliai, Tilžės g. 60-3"
        agent.state.diagnosis.verdicts["network"] = {"group": "B1", "reason": "billing_suspended"}
        turn_head(agent.state, agent.runtime, "Tai ne dėl to adresų skambinu")
        assert agent.state.identity.customer_id == "CUST101"  # NOT dropped yet
        assert agent.state.identity.reopen_confirm_utterance
        reply = scripted_words(agent.state, agent.runtime, "Tai ne dėl to adresų skambinu")
        assert reply and "tikrai" in reply  # the confirmation question
        # A-2 (2026-09-07): the ANSWER is read in pre_turn_guards (the turn head,
        # before the solver/walker can consume it) — mirror the live sequence.
        turn_head(agent.state, agent.runtime, "Taip, dėl kito adreso")
        assert agent.state.identity.customer_id is None  # identity dropped after the yes
        assert agent.state.diagnosis.verdicts == {}  # per-account conclusions dropped
        assert agent.state.turn.reopen_note is True
