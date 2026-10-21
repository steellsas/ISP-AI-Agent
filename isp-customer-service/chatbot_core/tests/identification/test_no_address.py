"""Kai adreso nėra — empty answers: a warning (address or account code), then a polite close
without a ticket (T-7, A-3).
"""

import pytest

from .helpers import _agent

FUNCTION = "Kai adreso nėra"


# --- from test_identification_rules.py ---


def test_empty_turns_warn_then_close_no_location(db_connection):
    from agent.decide.rules.reply import scripted_words

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.intake.anamnesis_asked = True  # adreso klausimas jau nuskambėjo
    r1 = scripted_words(agent.state, agent.runtime, "Nežinau adreso")
    assert not agent.state.closing.case_closed
    r2 = scripted_words(agent.state, agent.runtime, "Negaliu pasakyti")
    assert r2 and "negalėsiu" in r2  # PERSPĖJIMAS (su kodo užuomina)
    scripted_words(agent.state, agent.runtime, "Na nežinau")
    r4 = scripted_words(agent.state, agent.runtime, "Nieko nesakysiu")
    assert agent.state.closing.case_closed and r4 and "turiu baigti pokalbį" in r4  # U8: the reason
    assert agent.state.closing.is_complete  # the goodbye IS the end
    assert agent.state.ticket.ticket_id is None


def test_unrecognized_address_offers_code(db_connection):
    """Turinys yra, bet registras jo visai neatpažįsta — po 2 siūlom kodą
    (rev.2 2026-09-10: automatinių raidžių nebėra, fuzzy — pagrindinis)."""
    from agent.decide.rules.reply import scripted_words

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.intake.anamnesis_asked = True
    scripted_words(agent.state, agent.runtime, "Kosmonautų alėja 7")
    r = scripted_words(agent.state, agent.runtime, "Sakau — Kosmonautų alėja septyni")
    assert r and "abonento kodą" in r
    assert agent.state.identity.account_code_mode is True


def test_explicit_no_code_closes(db_connection):
    from agent.decide.rules.reply import scripted_words

    agent = _agent()
    agent.state.intake.problem_type = "internet_down"
    agent.state.identity.account_code_mode = True
    r = scripted_words(agent.state, agent.runtime, "Neturiu jokio kodo")
    assert agent.state.closing.case_closed and r and "abonentams" in r


class TestCannotNowDetector:
    """A-banga P1 (gyva #6 2026-09-04: „Ne patogu" ignoruotas): the cannot-now signal.
    (The v1 ladder that acted on it was gated on `resolution.procedure` and is gone.)"""

    def test_in_flow_negaliu_is_not_a_signal(self, db_connection):
        from agent.perceive.detectors import detect_cannot_now

        assert detect_cannot_now("Negaliu prisijungti prie interneto") is False
        assert detect_cannot_now("Negaliu rasti tos dėžutės") is False
        assert detect_cannot_now("Aš negaliu jį ieškoti, dabar esu ne namuose") is True
