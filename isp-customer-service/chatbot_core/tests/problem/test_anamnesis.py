"""Problema — Anamnezė."""

from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import (
    ClosingState,
    DiagnosisState,
    DialogState,
    GraphState,
    IdentityState,
    IntakeState,
    ResolutionState,
    TicketContext,
    TicketState,
    TurnScratch,
)

from tests.engine_fakes import as_call

FUNCTION = "Anamnezė"

# --- from test_fault_packs.py ---


class TestAnamnesisDirectives:
    """DIALOGO_ETALONAS #2 (2026-09-03): the OPENING anamnesis question is
    GONE — the ladder goes straight to the address; capture-first keeps what
    the opener already said; the targeted anamnesis lives in the packs."""

    def test_no_opening_question_straight_to_address(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        assert scripted_words(agent.state, agent.runtime, "Neveikia internetas") is None
        assert agent.state.intake.anamnesis_asked is True  # ladder-live marker stays
        assert agent.state.turn.directives.ident["kind"] in ("address_offer", "address_ask")
        block = context_card(agent.state, agent.runtime)
        assert "ANAMNEZĖS ŽINGSNIS" not in block
        assert "IDENTIFICATION STEP" in block

    def test_opening_capture_still_lands(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        scripted_words(agent.state, agent.runtime, "Neveikia internetas nuo vakar, po audros")
        assert agent.state.intake.anamnesis_when  # capture-first read the opener
        assert agent.state.intake.opening_heard_note is True

    def test_the_card_carries_the_contextual_anamnesis(self, db_connection):
        """Only the caller knows whether the power went out or a storm passed — and that is
        what explains a device dropping off the line."""
        from agent.contract import cards as catalog
        from agent.contract.locale import phrase

        need = catalog.card("no_mac_observed").needs["recent_events"]
        assert "elektra" in phrase(need.ask)
        assert "linijoje nesimato" in phrase(need.why)  # the telemetry context
