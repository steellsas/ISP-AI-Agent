"""Identifikacija — Identifikacijos pokalbis."""

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

FUNCTION = "Identifikacijos pokalbis"

# --- from test_fault_packs.py ---


class TestIdentificationF:
    """F (2026-08-20): identifikacija kaip pokalbis — pasakyk, ką radai ir ko
    ne; paragink su KODĖL; nesėkmę užfiksuok įraše."""

    def test_diag_street_found_house_not(self):
        from agent.execute.identification import address_diag_note

        note = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {"status": "ok", "matched": "Vilniaus g."},
                    "house": {"status": "not_found", "given": "39", "known_houses": [29, 31]},
                    "apartment": {"status": "skipped"},
                },
            }
        )
        assert note and "RANDU" in note and "39" in note and "29" in note

    def test_diag_street_elsewhere_and_fuzzy(self):
        from agent.execute.identification import address_diag_note

        note = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {
                        "status": "not_in_city",
                        "given": "Vilniaus g.",
                        "found_elsewhere": [{"city": "Kuršėnai"}],
                    },
                    "house": {"status": "skipped"},
                },
            }
        )
        assert note and "NERANDU" in note and "Kuršėnai" in note
        fuzzy = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {"status": "unclear", "fuzzy_candidates": ["Vytauto", "Vilniaus"]},
                    "house": {"status": "skipped"},
                },
            }
        )
        assert fuzzy and "Vytauto" in fuzzy
        assert address_diag_note({"success": False, "resolution": {}}) is None

    def test_diag_note_lands_in_facts_block(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.address_lookup_note = "- ADRESO PAIEŠKOS DIAGNOZĖ: gatvę RANDU, namo NĖRA."
        block = context_card(agent.state, agent.runtime)
        assert block and "ADRESO PAIEŠKOS DIAGNOZĖ" in block

    def test_encouragement_appears_once(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        agent.state.dialog.turn_count = 5
        first = context_card(agent.state, agent.runtime) or ""
        second = context_card(agent.state, agent.runtime) or ""
        assert "ADDRESS ENCOURAGEMENT" in first
        assert "ADDRESS ENCOURAGEMENT" not in second

    def test_failed_identification_lands_on_the_record(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.heard_utterances.extend(["neveikia internetas", "Vilnaus gatve kazkur"])
        summary = build_call_summary(agent.state, agent.runtime)
        fail = summary["identifikacija_nepavyko"]
        assert fail and "Vilnaus gatve kazkur" in fail["girdeta"]

    def test_short_ladder_phrases(self):
        from agent.contract.locale import phrase

        assert (
            phrase("identification.address_ask")
            == "Gerai — patikrinsiu ryšį iki jūsų buto. Koks adresas?"
        )
        assert "patikrinsiu ryšį" in phrase("identification.address_offer", address="X")


class TestIdentDirectives:
    """Zone 2: the transition to the address becomes a narrator goal directive;
    the OFFER question core stays verbatim (confirm guard); off reverts."""

    def _agent(self, candidate=True):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        if candidate:
            agent.state.identity.phone_candidate = {
                "customer_id": "CUST009",
                "name": "Test",
                "address": "Šiauliai, Vilniaus g. 29",
                "street": "Vilniaus g.",
                "house": "29",
                "apartment": None,
                "city": "Šiauliai",
            }
        return agent

    def test_offer_goes_to_narrator_with_verbatim_core(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "Vakar po audros dingo")
        assert reply is None
        idd = agent.state.turn.directives.ident
        assert idd and idd["kind"] == "address_offer" and "Vilniaus g. 29" in idd["adresas"]
        block = context_card(agent.state, agent.runtime)
        assert "Ar skambinate dėl Vilniaus g. 29?" in block  # verbatim core kept

    def test_ask_goes_to_narrator_without_candidate(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent(candidate=False)
        assert scripted_words(agent.state, agent.runtime, "Vakar po audros dingo") is None
        assert agent.state.turn.directives.ident["kind"] == "address_ask"
        assert "IDENTIFICATION STEP" in context_card(agent.state, agent.runtime)

    def test_off_switch_keeps_scripted_offer(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "Vakar po audros dingo")
        assert reply and "Ar skambinate dėl Vilniaus g. 29?" in reply
        assert agent.state.turn.directives.ident is None
