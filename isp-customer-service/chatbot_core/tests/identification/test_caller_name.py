"""Kas skambina — the caller's name and the holder check (T-12): the DB holder's name is never
said first; a mismatch is clarified without naming the holder.
"""

import json

import pytest

from tests.diagnosis.test_facts import BASE
from tests.diagnosis.test_step_refusal import _hear, _Tracer

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


# --- from test_live_1012.py ---


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("Labą dieną, esu Paulius, mane veikia internetas. Vilniaus gatvė, 33", "Paulius"),
        ("Labas, čia Jonas, neveikia internetas", "Jonas"),
        ("Čia kalba Ona", "Ona"),
        ("Aš esu darbe", None),
        ("čia Vilniaus g. 29", None),
        ("Panavardos sėra gėdras.", None),
    ],
)
def test_a3_a_name_given_unasked(said, name):
    from agent.perceive.caller import introduced_name

    assert introduced_name(said) == name


def test_a3_the_name_question_is_skipped(make_state, make_runtime):
    from agent.decide.rules.reply import plan_reply

    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    state.identity.result_pending = True
    state.intake.heard_utterances = ["Labą dieną, esu Paulius, neveikia internetas"]
    plan = plan_reply(state, rt, "Taip")

    assert state.identity.caller_name == "Paulius"
    assert plan is None or plan.rule != "identification.caller_name"


def test_a4_a_garbled_name_is_asked_again_once(make_state, make_runtime):
    from agent.decide.rules.head import caller_intro
    from agent.decide.rules.reply import plan_reply

    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST112"
    state.identity.result_pending = True
    caller_intro(state, rt, "Panavardos sėra gėdras.")

    assert state.identity.caller_name is None
    plan = plan_reply(state, rt, "Panavardos sėra gėdras.")
    assert plan.rule == "identification.caller_name" and "pakartoti" in plan.say.text

    caller_intro(state, rt, "Ėėė, nu")  # still nothing readable — no third ask
    assert state.identity.caller_name == "nenurodyta"


# --- from test_live_call_1014b.py ---


def test_tetas_is_family():
    from agent.perceive.caller import detect_caller_relation

    assert detect_caller_relation("Taip, Gedras vardu, tėtas mano.") == "family"


def _identified(make_state, phone="+37060030307", customer="CUST307"):
    state = make_state(phone)
    state.identity.customer_id = customer
    return state


# --- from test_live_calls_m6.py ---


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
        assert state.identity.caller_name is None  # asked once more (A4, 2026-10-12)
        caller_intro(state, make_runtime(), "po anas mano vardas.")
        assert state.identity.caller_name == "nenurodyta"
        assert state.identity.caller_name_heard is False


class _Tracer:
    session_id = "wave10"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def case_call(make_state, make_runtime):
    """A v2 Case call on a fault, the caller identified."""
    state, rt = make_state("+37060012353"), make_runtime(tracer=_Tracer())
    state.identity.customer_id = "CUST009"
    state.diagnosis.verdicts["network"] = {"reason": "no_mac_observed"}
    state.case.fault, state.case.solution = "no_mac_observed", 0
    return state, rt


# --- from test_wave10_quick.py ---


class TestV5OnlyTheCallersOwnNameCorrects:
    def _answer(self, case_call, heard):
        from agent.decide.rules.intake import _apply_caller_relation

        state, rt = case_call
        state.identity.caller_name = "Andrius"
        state.dialog.last_heard = heard
        state.turn.caller_relation_reading = "family"
        _apply_caller_relation(state, rt)
        return state.identity.caller_name

    def test_the_holders_name_is_not_the_caller(self, case_call):
        # live 2026-10-07: the caller became „Gedrius"
        assert self._answer(case_call, "Taip, mano tėtis Gedrius yra vardu.") == "Andrius"

    def test_a_garbled_word_is_not_a_name(self, case_call):
        assert self._answer(case_call, "Aršku ačių lauksu.") == "Andrius"

    def test_their_own_name_corrects(self, case_call):
        assert self._answer(case_call, "Ne, mano vardas Giedrius.") == "Giedrius"
