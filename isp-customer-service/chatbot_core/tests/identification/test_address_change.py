"""Adreso keitimas — after identification another address is taken only after the caller
confirms it (T-8, A-2, A-2R); „which address are we talking about?" is answered (A-2R-b).
"""

import pytest

from .helpers import _agent

FUNCTION = "Adreso keitimas"


# --- from test_identification_rules.py ---


class TestReopenConfirmation:
    """№3: adreso keitimas po identifikacijos — tik su patvirtinimu."""

    def _identified(self):
        agent = _agent(phone="+37060020112")
        agent.state.identity.customer_id = "CUST112"
        agent.state.identity.customer_address = "Šiauliai, Vilniaus g. 33-2"
        agent.state.intake.problem_type = "internet_down"
        return agent

    def test_correction_asks_before_reopening(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "iš tikrųjų skambinu dėl Tilžės g. 60"
        agent.state.identity.reopen_confirm_asked = False
        reply = scripted_words(agent.state, agent.runtime, "iš tikrųjų skambinu dėl Tilžės g. 60")
        assert reply and "tikrai" in reply and "Vilniaus g. 33-2" in reply
        assert agent.state.identity.customer_id == "CUST112"  # dar NEperjungta

    def test_yes_reopens_no_keeps(self, db_connection):
        from agent.decide.rules.head import turn_head

        # Atsakymą skaito pre_turn_guards (A-2: kad solveris/walker'is jo
        # nesuvartotų) — testas kviečia gyvą kelią.
        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "dėl Tilžės g. 60"
        agent.state.identity.reopen_confirm_asked = True
        turn_head(agent.state, agent.runtime, "Taip, dėl kito")
        assert agent.state.identity.customer_id is None  # atidaryta iš naujo

        agent2 = self._identified()
        agent2.state.identity.reopen_confirm_utterance = "dėl Tilžės g. 60"
        agent2.state.identity.reopen_confirm_asked = True
        turn_head(agent2.state, agent2.runtime, "Ne ne, likim prie šito")
        assert agent2.state.identity.customer_id == "CUST112"  # liko
        assert agent2.state.identity.reopen_confirm_utterance is None

    def test_unclear_answer_reasks_not_burns(self, db_connection):
        """A-2 gyva yda: neaiškus atsakymas klausimo nebesudegina — vienas
        pakartojimas, o walker'is tą turn'ą laikomas (hold)."""
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "dėl Tilžės g. 60"
        agent.state.identity.reopen_confirm_asked = True
        agent.state.identity.reopen_confirm_asks = 1
        turn_head(agent.state, agent.runtime, "Nu kaip čia dabar pasakyt")
        assert agent.state.identity.reopen_confirm_utterance is not None  # klausimas gyvas
        assert agent.state.dialog.resume_hold_due is True  # walker'is nesuvartos turn'o
        r = scripted_words(agent.state, agent.runtime, "Nu kaip čia dabar pasakyt")
        assert r and "KITO adreso" in r  # pakartojimas
        # Antras neaiškus — nurašom (liekam prie esamo), be amžino ciklo.
        turn_head(agent.state, agent.runtime, "Mhm chm")
        assert agent.state.identity.reopen_confirm_utterance is None
        assert agent.state.identity.customer_id == "CUST112"

    def test_address_question_is_answered(self, db_connection):
        """A-2b: „dėl kokio adreso mes bendraujame?" — agentas SAKO adresą
        (patvirtintas adresas nėra paslaptis; taip klientas pagauna klaidą)."""
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        r = scripted_words(agent.state, agent.runtime, "Dėl kokio adreso mes dabar bendraujame?")
        assert r and "Vilniaus g. 33-2" in r

    def test_confirmed_reopen_drops_bg_and_continues_ident(self, db_connection):
        """A-2R gyva yda: po „taip" foninis telemetrijos skaitymas atstatydavo
        senos sąskaitos diagnozę, o identifikacija nesitęsė — dabar bg išmetamas
        ir variklis IŠ KARTO bando naują adresą (Tilžės 60 → buto klausimas)."""
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.diagnosis.verdicts["network"] = {"group": "B6", "reason": "router_hung"}
        agent.state.turn.bg_diagnosis = '{"success": true}'
        agent.state.identity.phone_candidate = {"customer_id": "CUST112", "street": "Vilniaus g."}
        agent.state.identity.reopen_confirm_utterance = "mano adresas yra Tilžės gatvė 60"
        agent.state.identity.reopen_confirm_asked = True
        turn_head(agent.state, agent.runtime, "Taip taip, dėl KITO adreso skambinu")
        assert agent.state.identity.customer_id is None  # sena tapatybė numesta
        assert agent.state.turn.bg_diagnosis is None  # telemetrija išmesta kartu
        assert agent.state.diagnosis.verdicts == {}  # senų išvadų nebėra
        assert agent.state.identity.phone_candidate is None  # senas adresas nebesiūlomas
        assert agent.state.intake.problem_type == "internet_down"  # problema LIEKA
        # Tilžės 60 pabandyta iš karto → „koks butas?" nota reply sluoksniui.
        assert agent.state.turn.address_lookup_note or agent.state.turn.db_address_note

    def test_garbled_answer_does_not_stomp_good_pending_slots(self, db_connection):
        """P1 gyva: pending davė Tilžės 60 (conf 1.0), atsakymo darkymas
        „Tildžiai 660-3" jo nebeperrašo — resolve eina su 60."""
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "mano adresas yra Tilžės gatvė 60"
        agent.state.identity.reopen_confirm_asked = True
        turn_head(agent.state, agent.runtime, "Taip, dėl KITO adreso. Dėl Tildžiai 660-3.")
        assert agent.state.identity.profile.house.value == "60"  # ne 660

    def test_address_echo_question_freezes_counters(self, db_connection):
        """P3 gyva: „Taip." į adreso echo klausimą (net LLM'o žodžiais) —
        tikslinimas, ne tuščias turn'as."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Taigi, adresas yra Šiauliai, Tilžės g. 60, butas 3, taip?",
            }
        )
        from agent.decide.rules.identification import _account_code_rung

        handled, reply = _account_code_rung(agent.state, agent.runtime, agent.state, "Taip.")
        assert handled is False and reply is None
        assert agent.state.identity.address_empty_turns == 0

    def test_confirmed_reopen_commits_single_contract_address(self, db_connection):
        """Naujas adresas (Vilniaus g. 29) — po „taip" į pakeitimą adresas dar
        pakartojamas (F-6), ir tik antras „taip" jį identifikuoja."""
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "skambinu dėl Vilniaus gatvės 29"
        agent.state.identity.reopen_confirm_asked = True
        turn_head(agent.state, agent.runtime, "Taip")
        assert agent.state.identity.customer_id is None
        assert agent.state.dialog.active_question.key == "address_heard_confirm"
        turn_head(agent.state, agent.runtime, "Taip")
        assert agent.state.identity.customer_id == "CUST009"  # nauja sutartis prisirišo

    def test_address_question_mid_ident_names_heard_address(self, db_connection):
        """A-2R-b gyva: „kokiu adresu bendraujam?" PO reopen (klientas numestas,
        adresas slotuose) — agentas sako, KĄ tikslina, ne improvizuoja."""
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        from agent.slots import SlotStatus

        agent.state.identity.profile.street.propose("Tilžės g.", 1.0, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("60", 1.0, SlotStatus.HEARD)
        r = scripted_words(
            agent.state, agent.runtime, "Tai kokiu adresu dabar bendraujam, tikrinam?"
        )
        assert r and "Tilžės g. 60" in r and "dėl šio adreso" in r

    def test_address_question_mid_ident_without_slots(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        r = scripted_words(
            agent.state, agent.runtime, "Galite pasakyti tikslų adresą, kur tikrinat?"
        )
        assert r and "nenustat" in r

    def test_yes_to_heard_address_commits_from_slots(self, db_connection):
        """„Taip" į „ar skambinate dėl šio adreso?" be telefono kandidato —
        variklis riša iš slotų (vienos sutarties adresas prisiriša iš karto)."""
        from agent.decide.rules.head import turn_head

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        from agent.slots import SlotStatus

        agent.state.identity.profile.street.propose("Vilniaus g.", 1.0, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("29", 1.0, SlotStatus.HEARD)
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Girdėjau adresą Vilniaus g. 29, bet dar nepatvirtinau. Ar skambinate dėl šio adreso?",
            }
        )
        turn_head(agent.state, agent.runtime, "Taip taip.")
        assert agent.state.identity.customer_id == "CUST009"

    def test_bg_diagnosis_never_applies_without_customer(self, db_connection):
        agent = _agent()
        agent.state.turn.bg_diagnosis = '{"success": true}'
        from agent.background import apply_bg_diagnosis

        apply_bg_diagnosis(agent.state, agent.runtime)
        assert agent.state.turn.bg_diagnosis is None
        assert agent.state.diagnosis.verdicts == {}


class TestOtherStreetSignal:
    """A-banga P2 (gyva #4: „mano ADARAS yra Tilžės gatvė 60"): kitos registro
    gatvės vardas + skaitmuo po identifikacijos = korekcijos kandidatas."""

    def _identified(self):
        agent = _agent()
        agent.state.identity.customer_id = "CUST112"
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.set_customer(
            "CUST112", "Paulius Vasiliauskas", "Šiauliai, Vilniaus g. 33-2"
        )
        return agent

    def _turn(self, agent, text):
        from agent.decide.rules.head import turn_head

        from tests.calls import hear

        # Gyva seka: prefill, tada pre_turn_guards —
        # reopen trigeris gyvena guards'uose, ne prefill'e.
        hear(agent, text)
        turn_head(agent.state, agent.runtime, text)

    def test_garbled_correction_triggers_confirm(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        msg = "Atsiprašau su maišiu, mano adaras yra Tilžės gatvė 60"
        self._turn(agent, msg)
        assert agent.state.identity.reopen_confirm_utterance  # kandidatas užfiksuotas
        r = scripted_words(agent.state, agent.runtime, msg)
        assert r and "KITO adreso" in r  # patvirtinimo klausimas

    def test_own_street_number_is_content(self, db_connection):
        agent = self._identified()
        self._turn(agent, "Nei 1 lemputė nedega ant to routerio")
        assert not agent.state.identity.reopen_confirm_utterance

    def test_no_digit_no_trigger(self, db_connection):
        agent = self._identified()
        self._turn(agent, "Kaimynas iš Tilžės gatvės sakė tas pats")
        assert not agent.state.identity.reopen_confirm_utterance
