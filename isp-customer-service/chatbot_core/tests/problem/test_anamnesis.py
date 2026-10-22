"""Problema — Anamnezė."""

import pytest
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


WHEN = [
    pytest.param("vakar vakare", {"when": "yesterday"}, id="vakar"),
    pytest.param("prieš valandą", {"when": "hour_ago"}, id="prieš valandą"),
    pytest.param("šiandien", {"when": "today"}, id="šiandien"),
    pytest.param("jau kelios dienos", {"when": "days_ago"}, id="kelios dienos"),
    pytest.param("nežinau", {"when": "unknown"}, id="nežino"),
    pytest.param("po audros", {"trigger": "storm"}, id="po audros"),
    pytest.param("kai dingo elektra", {"trigger": "power_cut"}, id="dingus elektrai"),
    pytest.param("po remonto", {"trigger": "renovation"}, id="po remonto"),
    pytest.param(
        "nuo vakar vakaro, po audros",
        {"when": "yesterday", "trigger": "storm"},
        id="kada ir po ko kartu",
    ),
    pytest.param(
        "nuo ryto",
        {"when": "today"},
        id="nuo ryto",
        marks=pytest.mark.xfail(strict=True, reason="„nuo ryto“ neatpažįstama kaip laikas"),
    ),
    pytest.param(
        "kai perkėliau routerį",
        {"trigger": "device_moved"},
        id="perkėlus routerį",
        marks=pytest.mark.xfail(strict=True, reason="routerio perkėlimas nėra tarp priežasčių"),
    ),
]


@pytest.mark.parametrize(("said", "expect"), WHEN)
def test_when_and_after_what(said, expect):
    """Kada ir po ko dingo"""
    from agent.perceive.nlu import extract_anamnesis

    got = extract_anamnesis(said)
    assert {k: got[k] for k in expect} == expect


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
