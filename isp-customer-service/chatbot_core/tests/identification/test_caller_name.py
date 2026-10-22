"""Kas skambina — the caller's name and the holder check (T-12): the DB holder's name is never
said first; a mismatch is clarified without naming the holder.
"""

import pytest

from .helpers import _agent

FUNCTION = "Kas skambina"


# --- from test_identification_rules.py ---


class TestHolderNameCheck:
    """№4: sakosi savininkas kitu vardu → patikslinimas BE DB vardo."""

    def test_fuzzy_match_tolerates_stt(self, db_connection):
        from agent.perceive.caller import holder_name_matches

        agent = _agent()
        agent.state.identity.customer_name = "Andrius Pilienius"
        assert holder_name_matches(agent.state, agent.runtime, "Andrijus") is True  # STT darkymas
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        assert holder_name_matches(agent.state, agent.runtime, "Petras") is False
        agent.state.identity.customer_name = None
        assert (
            holder_name_matches(agent.state, agent.runtime, "Bet kas") is True
        )  # nėra su kuo lyginti

    def test_mismatch_asks_scripted_and_nameless(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.caller_name = "Petras"
        agent.state.identity.holder_clarify_open = True
        agent.state.identity.holder_clarify_asked = False
        reply = scripted_words(agent.state, agent.runtime, "Petras, aš savininkas")
        assert reply and "kitu vardu" in reply  # scripted, deterministinis
        assert "Giedri" not in reply  # DB vardas NIEKADA negarsinamas

    def test_a_name_that_does_not_match_is_clarified_even_unasked(self, db_connection):
        """Wave 6 (Andrius 2026-10-01: *„pasimetė vardo patikslinimas"*): the caller never
        claims the contract is theirs — they just give a name, and it is not the holder's.
        That is enough for ONE polite clarification; the DB name still stays unsaid."""
        from agent.decide.rules.head import caller_intro

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.result_pending = True

        caller_intro(agent.state, agent.runtime, "Darius.")

        assert agent.state.identity.caller_name == "Darius"
        assert agent.state.identity.caller_relation == "unknown"  # jis nieko nesakė apie sutartį
        # 2026-10-14 (Andrius): first as a mishearing — „ar teisingai išgirdau?" — like the
        # address; the contract question comes only when the name stands.
        assert agent.state.identity.name_confirm_open is True
        assert agent.state.identity.holder_clarify_open is False

    def test_a_caller_who_said_who_they_are_is_not_quizzed(self, db_connection):
        """„Žmonos vardu sudaryta" already explains the mismatch — asking again is noise."""
        from agent.decide.rules.head import caller_intro

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.result_pending = True

        caller_intro(agent.state, agent.runtime, "Darius, sutartis žmonos vardu.")

        assert agent.state.identity.caller_relation == "family"
        assert agent.state.identity.holder_clarify_open is False

    def test_a_thank_you_is_not_a_name(self, db_connection):
        """Eval 2026-10-01: „Aišku, ačiū, lauksiu" buvo užrašyta kaip vardas „Aišku" — ir dar
        paklausta dėl sutarties savininko. Padėka nėra vardas, tad ir patikslinimo nėra."""
        from agent.decide.rules.head import caller_intro

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.result_pending = True

        caller_intro(agent.state, agent.runtime, "Aišku, ačiū, lauksiu")
        # 2026-10-12 (A4): nothing readable is asked once more, not guessed …
        assert agent.state.identity.caller_name is None
        assert agent.state.identity.caller_name_reasked
        caller_intro(agent.state, agent.runtime, "Aišku, ačiū, lauksiu")

        assert agent.state.identity.caller_name == "nenurodyta"  # … and then let go
        assert agent.state.identity.holder_clarify_open is False

    def test_the_clarification_is_its_own_turn(self, db_connection):
        """2026-10-14 (Andrius): identification ends before the finding — the clarification no
        longer rides along with it; it is a scripted turn of its own, the name unsaid."""
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import _goal_holder_clarify

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.caller_name = "Tomas"
        agent.state.identity.holder_clarify_open = True

        said = scripted_words(agent.state, agent.runtime, "Tomas")

        assert said and "kitu vardu" in said
        assert "Giedri" not in said  # DB vardas NIEKADA negarsinamas
        assert _goal_holder_clarify(agent.state, agent.runtime) == []  # nebeprisideda prie kito

    def test_clarify_answer_updates_relation(self, db_connection):
        from tests.calls import hear

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.caller_name = "Petras"
        agent.state.identity.caller_relation = "holder"
        agent.state.identity.holder_clarify_open = True
        agent.state.identity.holder_clarify_asked = True  # klausimas jau nuskambėjo
        hear(agent, "Žmonos vardu sudaryta sutartis")
        assert agent.state.identity.caller_relation != "holder"


class TestNameConfirm:
    """2026-10-14 (Andrius): „išgirdau Giedris — Giedrius sakiau — malonu, Giedriau". The name
    is checked like the address, and the finding waits until identification is done."""

    @pytest.mark.parametrize(
        ("heard", "spelled"),
        [("Gedrus", "Giedrius"), ("Giedris", "Giedrius"), ("Malabartas", None), ("Petras", None)],
    )
    def test_a_garbled_name_takes_the_holders_spelling(self, db_connection, heard, spelled):
        from agent.perceive.caller import holder_spelling

        agent = _agent()
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        assert holder_spelling(agent.state, heard) == spelled

    def test_paulus_is_paulius(self, db_connection):
        from agent.perceive.caller import holder_spelling

        agent = _agent()
        agent.state.identity.customer_name = "Paulius Kazlauskas"
        assert holder_spelling(agent.state, "Paulus") == "Paulius"

    def _mismatch(self):
        from agent.decide.rules.head import caller_intro
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.customer_name = "Giedrius Giedraitis"
        agent.state.identity.result_pending = True
        caller_intro(agent.state, agent.runtime, "Darius.")
        said = scripted_words(agent.state, agent.runtime, "Darius.")
        assert said and "ar teisingai išgirdau" in said.lower() and "Darius" in said
        assert agent.state.identity.name_confirm_asked is True
        return agent

    def test_yes_opens_the_contract_question(self, db_connection):
        from agent.decide.rules.head import name_confirm_answer

        agent = self._mismatch()
        assert name_confirm_answer(agent.state, agent.runtime, "Taip") is True
        assert agent.state.identity.name_confirm_open is False
        assert agent.state.identity.holder_clarify_open is True
        assert agent.state.identity.holder_clarify_soft is False

    def test_a_corrected_name_that_matches_ends_it(self, db_connection):
        from agent.decide.rules.head import name_confirm_answer

        agent = self._mismatch()
        name_confirm_answer(agent.state, agent.runtime, "Ne, Giedrius")
        assert agent.state.identity.caller_name == "Giedrius"
        assert agent.state.identity.holder_clarify_open is False
        assert agent.state.identity.name_confirm_open is False

    def test_no_asks_the_name_again(self, db_connection):
        from agent.decide.rules.head import name_confirm_answer

        agent = self._mismatch()
        name_confirm_answer(agent.state, agent.runtime, "Ne")
        assert agent.state.identity.caller_name is None
        assert agent.state.identity.caller_name_reasked is True

    def test_the_finding_waits(self, db_connection):
        from agent.decide.rules.case_rule import _identification_owns_the_turn
        from agent.phase import IDENTIFY, phase_of

        agent = self._mismatch()
        agent.state.identity.result_pending = False
        agent.state.dialog.last_heard = "Darius."
        agent.state.intake.problem_type = "no_internet"
        assert _identification_owns_the_turn(agent.state) is True
        assert phase_of(agent.state) == IDENTIFY

    def test_the_relation_in_the_answer_ends_it(self, db_connection):
        from agent.decide.rules.head import name_confirm_answer

        agent = self._mismatch()
        name_confirm_answer(agent.state, agent.runtime, "Žmonos vardu sudaryta sutartis")
        assert agent.state.identity.caller_name == "Darius"
        assert agent.state.identity.caller_relation == "family"
        assert agent.state.identity.holder_clarify_open is False

    def test_a_question_instead_of_an_answer_lets_the_name_stand(self, db_connection):
        """Eval S1v: „O sakykite, ar šitas skambutis man kainuos?" is not a „no"."""
        from agent.decide.rules.head import name_confirm_answer

        agent = self._mismatch()
        owns = name_confirm_answer(
            agent.state, agent.runtime, "O sakykite, ar šitas skambutis man kainuos?"
        )
        assert owns is False  # the question is answered by the rest of the turn
        assert agent.state.identity.caller_name == "Darius"
        assert agent.state.identity.holder_clarify_open is True
