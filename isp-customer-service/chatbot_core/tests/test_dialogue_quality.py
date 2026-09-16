"""
W0–W2 dialogue-quality waves (Andrius 2026-08-25): order guards after the
garbled-call analysis, hear-the-caller mechanics, and the quiet analyst.
"""

from types import SimpleNamespace

from agent.delivery import apply_delivery
from agent.evidence import Contradiction
from agent.graph_v2.state import TicketContext


def _turn_state(agent, text):
    """The agent's state as a node input for one caller turn."""
    from agent.graph_v2.state import TurnScratch

    return agent.state.model_copy(update={"turn": TurnScratch(user_input=text)})


class TestW0OrderGuards:
    """W0 (live 2026-08-25): the solver's legacy bridge path fired mid-power
    talk on a garbled 'vėl įkišau'; question-shaped ticket answers bypassed
    the capture; the scripted goodbye never ended the call."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_power"}
        return agent

    def test_bridge_fix_waits_for_the_offer(self, db_connection):
        from agent.decide.rules.diagnosis import drive_propose_fix

        agent = self._agent()
        agent.state.resolution.bridge_plug_reported = True  # poisoned by a garbled power reseat
        reply = drive_propose_fix(agent.state, agent.runtime, "", "ištraukiau ir vėl įkišau")
        assert "Ar turite kompiuterį?" in reply
        assert agent.state.resolution.bridge_plug_reported is False  # the false memory cleared
        assert agent.state.resolution.bridge_offered is True

    def test_power_reseat_is_not_a_bridge_plug(self, db_connection):
        from agent.decide.rules.diagnosis import plug_report

        agent = self._agent()
        assert (
            plug_report(agent.state, agent.runtime, "ištraukiau ir vėl įkišau") is False
        )  # no computer context

    def test_kur_questions_are_on_task(self):
        from agent.perceive.side_topic import is_howto

        assert is_howto("Kur įkišti iki galo? Nesupratau.")
        assert is_howto("Kur žiūrėti tą lemputę?")

    def test_question_shaped_hours_answer_is_captured(self, db_connection):
        from agent.decide.rules.head import turn_head

        agent = self._agent()
        agent.state.ticket.stage = "hours"
        agent.state.ticket.context = TicketContext(step_id=None, hours_asked=True, intro_done=True)
        turn_head(agent.state, agent.runtime, "Kodėl tokiausia skambinti nuo 17-18 val.")
        assert agent.state.ticket.contact_hours and "17-18" in agent.state.ticket.contact_hours
        assert agent.state.ticket.stage == "done"

    def test_real_question_without_content_still_diverts(self, db_connection):
        from agent.decide.rules.head import turn_head

        agent = self._agent()
        agent.state.ticket.stage = "hours"
        agent.state.ticket.context = TicketContext(step_id=None, hours_asked=True, intro_done=True)
        turn_head(agent.state, agent.runtime, "Kodėl jums reikia mano laiko?")
        assert not agent.state.ticket.contact_hours
        assert agent.state.turn.ticket_offscript_question is True

    def test_scripted_goodbye_ends_the_call(self, db_connection):
        from agent.tools import create_ticket
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        agent = self._agent()
        res = create_ticket("CUST009", "network_issue", "test")
        agent.state.ticket.ticket_id = res["ticket_id"]
        agent.state.closing.case_closed = True
        runtime = Runtime(context=agent.runtime)
        upd = run_turn_nodes(_turn_state(agent, "Gerai, ačiū"), runtime)
        assert upd["closing"].is_complete is True  # one goodbye, then hang up


class TestW1LivingDialogue:
    """W1 (Andrius 2026-08-25): hear the caller — the opening's anamnesis is
    read instead of re-asked; a story-flipping volunteered fact is confirmed
    before it may poison the ledger."""

    def test_opening_anamnesis_skips_the_question(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        reply = scripted_words(
            agent.state,
            agent.runtime,
            "Laba diena, neveikia internetas. Vakar dingo, šiandien nebėra.",
        )
        assert reply is None
        assert agent.state.intake.anamnesis_raw and agent.state.intake.anamnesis_when
        assert agent.state.turn.directives.ident["kind"] in ("address_offer", "address_ask")
        block = context_card(agent.state, agent.runtime) or ""
        assert "THE CALLER ALREADY SAID" in block and "do NOT ask when it broke" in block

    def test_opening_without_when_goes_to_address(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        # etalonas #2 (2026-09-03): no opening anamnesis question — the flow
        # goes straight to the address; targeted anamnesis lives in the packs.
        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        assert scripted_words(agent.state, agent.runtime, "Neveikia internetas pas mane") is None
        assert agent.state.turn.directives.ident["kind"] in ("address_offer", "address_ask")

    def _resolving_agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_power"}
        return agent

    def test_story_flipping_volunteered_fact_is_parked(self, db_connection, monkeypatch):
        # Live the poisoned fact came from the UNDERSTAND pass; tests run with
        # the pass off, so the keyword reader is stubbed to deliver the same.
        import agent.evidence as ev
        from agent.decide.rules.evidence import evidence_drive
        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setattr(
            ev,
            "extract_client_facts",
            lambda t: {"lights": "off", "outlet_works": "not_working"} if t else {},
        )
        agent = self._resolving_agent()
        agent.state.diagnosis.pending_evidence_key = "lights"  # we asked about the LIGHTS
        ingest_client_evidence(agent.state, agent.runtime, "nedega nė viena, ir rozetė neveikia")
        assert agent.state.diagnosis.evidence.get("lights", {}).get("value") == "off"
        assert agent.state.diagnosis.evidence.get("outlet_works") is None  # parked, not committed
        assert agent.state.diagnosis.contradiction == Contradiction(
            kind="flip", fact_key="outlet_works", now_value="not_working"
        )
        reply = evidence_drive(agent.state, agent.runtime, "nedega nė viena, ir rozetė neveikia")
        assert reply and "sitikinti" in reply  # the one confirm question
        assert agent.state.diagnosis.contradiction == Contradiction(
            kind="flip", fact_key="outlet_works", now_value="not_working", asked=True
        )

    def test_confirmed_gate_commits_denied_gate_drops(self, db_connection):
        from agent.perceive.evidence import ingest_client_evidence

        agent = self._resolving_agent()
        agent.state.diagnosis.contradiction = Contradiction(
            kind="flip", fact_key="outlet_works", now_value="not_working", asked=True
        )
        ingest_client_evidence(agent.state, agent.runtime, "Taip, tikrai neveikia")
        assert agent.state.diagnosis.evidence.get("outlet_works", {}).get("value") == "not_working"
        agent2 = self._resolving_agent()
        agent2.state.diagnosis.contradiction = Contradiction(
            kind="flip", fact_key="outlet_works", now_value="not_working", asked=True
        )
        ingest_client_evidence(agent2.state, agent2.runtime, "Ne ne, rozetė veikia, viskas gerai")
        assert (agent2.state.diagnosis.evidence.get("outlet_works") or {}).get(
            "value"
        ) != "neveikia"

    def test_direct_answer_is_not_gated(self, db_connection, monkeypatch):
        import agent.evidence as ev
        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setattr(
            ev, "extract_client_facts", lambda t: {"outlet_works": "not_working"} if t else {}
        )
        agent = self._resolving_agent()
        agent.state.diagnosis.pending_evidence_key = "outlet_works"  # we ASKED about the outlet
        ingest_client_evidence(agent.state, agent.runtime, "neveikia rozetė")
        assert agent.state.diagnosis.evidence.get("outlet_works", {}).get("value") == "not_working"
        assert agent.state.diagnosis.contradiction is None


class TestUnheardQuestion:
    """Andrius 2026-08-26: the agent must never believe it asked a question
    the caller could not hear — an unheard '?' rolls the ask back and the
    narrator reacts + re-asks."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 1},
        }
        agent.state.messages.append({"role": "assistant", "content": "irrelevant"})
        return agent

    def test_unheard_question_rolls_the_ask_back(self, db_connection):
        from agent.speak.context_card import context_card

        agent = self._agent()
        agent.state.dialog.last_question = "Ar dega bent viena lemputė?"
        agent.state.diagnosis.pending_evidence_key = "lights"
        agent.state.diagnosis.evidence_ask_counts = {"lights": 1}
        apply_delivery(
            agent.state, agent.runtime, ["Gerai, kad radote.", "Ar dega bent viena lemputė?"], 1
        )
        assert agent.state.dialog.last_question is None
        # the pending key STAYS (live 2026-08-27: clearing it looped the call —
        # the interrupting ANSWER had no key to land on); only the ask counter
        # steps back.
        assert agent.state.diagnosis.pending_evidence_key == "lights"
        assert agent.state.diagnosis.evidence_ask_counts["lights"] == 0
        assert agent.state.resolution.procedure["presented"]["dr_lights"] == 0
        assert agent.state.voice.unheard_question == "Ar dega bent viena lemputė?"
        assert agent.state.voice.undelivered_tail is None  # superseded by the strong note
        block = context_card(agent.state, agent.runtime) or ""
        assert "YOUR QUESTION NEVER WENT OUT" in block and "lemputė" in block
        assert "KLAUSIMAS NEIŠĖJO" not in (context_card(agent.state, agent.runtime) or "")

    def test_heard_question_keeps_the_ask(self, db_connection):
        agent = self._agent()
        agent.state.dialog.last_question = "Ar dega bent viena lemputė?"
        agent.state.diagnosis.pending_evidence_key = "lights"
        agent.state.diagnosis.evidence_ask_counts = {"lights": 1}
        apply_delivery(
            agent.state,
            agent.runtime,
            ["Ar dega bent viena lemputė?", "Tai parodys, ar gauna srovę."],
            1,
        )
        assert agent.state.dialog.last_question == "Ar dega bent viena lemputė?"
        assert agent.state.diagnosis.pending_evidence_key == "lights"
        assert agent.state.voice.unheard_question is None
        assert agent.state.voice.undelivered_tail  # the plain advisory note stands


class TestW2QuietAnalyst:
    """W2: background advisory notes — wording only, one-shot, off-switch."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.customer_id = "CUST009"
        agent.state.messages.append({"role": "user", "content": "neveikia internetas"})
        return agent

    def test_notes_parsed_filtered_and_consumed_once(self, db_connection, monkeypatch):
        import src.services.llm.client as llm
        from agent.speak.context_card import context_card

        monkeypatch.setenv("ANALYST", "on")
        monkeypatch.setattr(
            llm,
            "llm_completion",
            lambda **k: (
                "- klientas jau pasake, kada dingo\n"
                "- OK\n"
                "- paprasykite kliento patikrinti maitinima\n"  # ACTION -> dropped
                "- faktas priestarauja tam, ka klientas kartoja"
            ),
        )
        from agent.analyst import run_analyst

        agent = self._agent()
        notes = run_analyst(agent.state, agent.runtime)
        assert notes == [
            "klientas jau pasake, kada dingo",
            "faktas priestarauja tam, ka klientas kartoja",
        ]
        agent.state.voice.analyst_notes = notes  # the session hands them to the next turn
        block = context_card(agent.state, agent.runtime) or ""
        assert "ANALYST NOTES" in block and "paprasykite" not in block
        assert "TYLIOJO ANALITIKO" not in (context_card(agent.state, agent.runtime) or "")

    def test_off_switch_and_ok_reply(self, db_connection, monkeypatch):
        import src.services.llm.client as llm
        from agent.analyst import run_analyst

        calls = []
        monkeypatch.setattr(llm, "llm_completion", lambda **k: calls.append(1) or "OK")
        monkeypatch.setenv("ANALYST", "off")
        agent = self._agent()
        assert run_analyst(agent.state, agent.runtime) is None
        assert calls == []
        monkeypatch.setenv("ANALYST", "on")
        assert run_analyst(agent.state, agent.runtime) is None  # OK -> no notes
        assert calls == [1]


class TestTurnGrammar:
    """Etalono 2 zingsnis (2026-09-03): reakcija nesa REIKSME (reiskia:),
    vardo priemimas, adreso perejimas be suolio."""

    def _agent(self, verdict="router_hung"):
        from tests.calls import make_agent

        agent = make_agent("+37060020112")
        agent.state.identity.customer_id = "CUST112"
        agent.state.intake.problem_type = "internet_down"
        agent.state.resolution.procedure = {"verdict": verdict, "step": "rh_scope"}
        return agent

    def test_fact_meaning_note_is_one_shot(self, db_connection):
        from agent.perceive.evidence import _note_fact_meaning
        from agent.speak.context_card import context_card

        agent = self._agent()
        _note_fact_meaning(agent.state, agent.runtime, "fail_scope", "all")
        block = context_card(agent.state, agent.runtime) or ""
        assert "THIS MEANS" in block and "router itself has most likely hung" in block
        assert "TAI REIŠKIA" not in (context_card(agent.state, agent.runtime) or "")  # one-shot

    def test_fact_meaning_silent_without_declaration(self, db_connection):
        from agent.perceive.evidence import _note_fact_meaning

        agent = self._agent(verdict="no_mac_observed")
        _note_fact_meaning(
            agent.state, agent.runtime, "power_cable", "įkištas"
        )  # no reiskia declared
        assert agent.state.diagnosis.fact_meaning is None

    def test_mires_lights_meaning_declared(self, db_connection):
        from agent.perceive.evidence import _note_fact_meaning
        from agent.speak.context_card import context_card

        agent = self._agent(verdict="no_mac_observed")
        _note_fact_meaning(agent.state, agent.runtime, "lights", "on")
        assert "the line does not see it" in (context_card(agent.state, agent.runtime) or "")

    def test_name_acceptance_is_one_shot(self, db_connection):
        from agent.speak.context_card import context_card

        agent = self._agent()
        agent.state.identity.caller_name = "Tomas"
        agent.state.identity.caller_name_heard = True
        block = context_card(agent.state, agent.runtime) or ""
        assert "Malonu, Tomas" in block
        assert "Malonu" not in (context_card(agent.state, agent.runtime) or "")

    def test_address_offer_directive_reacts_first(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("+37060020112")
        agent.state.intake.problem_type = "internet_down"
        agent.state.turn.directives.ident = {
            "kind": "address_offer",
            "adresas": "Tilžės g. 60, butas 7",
            "fallback": "Ar skambinate dėl Tilžės g. 60, butas 7?",
        }
        block = context_card(agent.state, agent.runtime) or ""
        assert "heard what the caller said" in block  # reakcija pirmiau
        assert "Suprantu — dingo internetas" in block  # problemos aidas
        assert "„Ar skambinate dėl Tilžės g. 60, butas 7?“" in block  # šerdis
