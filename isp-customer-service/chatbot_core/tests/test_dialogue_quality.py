"""
W0–W2 dialogue-quality waves (Andrius 2026-08-25): order guards after the
garbled-call analysis, hear-the-caller mechanics, and the quiet analyst.
"""

from types import SimpleNamespace


class TestW0OrderGuards:
    """W0 (live 2026-08-25): the solver's legacy bridge path fired mid-power
    talk on a garbled 'vėl įkišau'; question-shaped ticket answers bypassed
    the capture; the scripted goodbye never ended the call."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_power"}
        return agent

    def test_bridge_fix_waits_for_the_offer(self, db_connection):
        agent = self._agent()
        agent._bridge_plug_reported = True  # poisoned by a garbled power reseat
        reply = agent._drive_propose_fix("", "ištraukiau ir vėl įkišau")
        assert "Ar turite kompiuterį?" in reply
        assert agent._bridge_plug_reported is False  # the false memory cleared
        assert agent._drive_bridge_offered is True

    def test_power_reseat_is_not_a_bridge_plug(self, db_connection):
        agent = self._agent()
        assert agent._plug_report("ištraukiau ir vėl įkišau") is False  # no computer context

    def test_kur_questions_are_on_task(self):
        from agent.perception_flow import is_howto

        assert is_howto("Kur įkišti iki galo? Nesupratau.")
        assert is_howto("Kur žiūrėti tą lemputę?")

    def test_question_shaped_hours_answer_is_captured(self, db_connection):
        agent = self._agent()
        agent._ticket_stage = "hours"
        agent._ticket_ctx = {"step": None, "hours_asked": True, "intro_done": True}
        agent._pre_turn_guards("Kodėl tokiausia skambinti nuo 17-18 val.")
        assert agent.state.contact_hours and "17-18" in agent.state.contact_hours
        assert agent._ticket_stage == "done"

    def test_real_question_without_content_still_diverts(self, db_connection):
        agent = self._agent()
        agent._ticket_stage = "hours"
        agent._ticket_ctx = {"step": None, "hours_asked": True, "intro_done": True}
        agent._pre_turn_guards("Kodėl jums reikia mano laiko?")
        assert not agent.state.contact_hours
        assert agent._ticket_offscript is True

    def test_scripted_goodbye_ends_the_call(self, db_connection):
        from agent.graph_v2.nodes.closing import make_closing_node
        from agent.tools import create_ticket

        agent = self._agent()
        res = create_ticket("CUST009", "network_issue", "test")
        agent.state.ticket_id = res["ticket_id"]
        agent.state.case_closed = True
        node = make_closing_node(agent)
        node(SimpleNamespace(turn=SimpleNamespace(user_input="Gerai, ačiū")))
        assert agent.state.is_complete is True  # one goodbye, then hang up


class TestW1LivingDialogue:
    """W1 (Andrius 2026-08-25): hear the caller — the opening's anamnesis is
    read instead of re-asked; a story-flipping volunteered fact is confirmed
    before it may poison the ledger."""

    def test_opening_anamnesis_skips_the_question(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        reply = agent._identification_scripted_reply(
            "Laba diena, neveikia internetas. Vakar dingo, šiandien nebėra."
        )
        assert reply is None
        assert agent.state.anamnesis_raw and agent.state.anamnesis_when
        assert agent._ident_directive["kind"] in ("address_offer", "address_ask")
        block = agent._state_facts_block() or ""
        assert "KLIENTAS JAU PASAKĖ" in block and "NEKLAUSK" in block

    def test_opening_without_when_still_asks(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        assert agent._identification_scripted_reply("Neveikia internetas pas mane") is None
        assert agent._ident_directive["kind"] == "anamnesis"

    def _resolving_agent(self):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_power"}
        return agent

    def test_story_flipping_volunteered_fact_is_parked(self, db_connection, monkeypatch):
        # Live the poisoned fact came from the UNDERSTAND pass; tests run with
        # the pass off, so the keyword reader is stubbed to deliver the same.
        import agent.evidence as ev

        monkeypatch.setattr(
            ev,
            "extract_client_facts",
            lambda t: {"lights": "nedega", "outlet_works": "neveikia"} if t else {},
        )
        agent = self._resolving_agent()
        agent._evidence_last_ask_key = "lights"  # we asked about the LIGHTS
        agent._ingest_client_evidence("nedega nė viena, ir rozetė neveikia")
        assert agent.state.evidence.get("lights", {}).get("value") == "nedega"
        assert agent.state.evidence.get("outlet_works") is None  # parked, not committed
        assert agent._fact_confirm == ("outlet_works", "neveikia")
        reply = agent._evidence_drive("nedega nė viena, ir rozetė neveikia")
        assert reply and "sitikinti" in reply  # the one confirm question
        assert agent._fact_confirm_asked == ("outlet_works", "neveikia")

    def test_confirmed_gate_commits_denied_gate_drops(self, db_connection):
        agent = self._resolving_agent()
        agent._fact_confirm_asked = ("outlet_works", "neveikia")
        agent._ingest_client_evidence("Taip, tikrai neveikia")
        assert agent.state.evidence.get("outlet_works", {}).get("value") == "neveikia"
        agent2 = self._resolving_agent()
        agent2._fact_confirm_asked = ("outlet_works", "neveikia")
        agent2._ingest_client_evidence("Ne ne, rozetė veikia, viskas gerai")
        assert (agent2.state.evidence.get("outlet_works") or {}).get("value") != "neveikia"

    def test_direct_answer_is_not_gated(self, db_connection, monkeypatch):
        import agent.evidence as ev

        monkeypatch.setattr(
            ev, "extract_client_facts", lambda t: {"outlet_works": "neveikia"} if t else {}
        )
        agent = self._resolving_agent()
        agent._evidence_last_ask_key = "outlet_works"  # we ASKED about the outlet
        agent._ingest_client_evidence("neveikia rozetė")
        assert agent.state.evidence.get("outlet_works", {}).get("value") == "neveikia"
        assert agent._fact_confirm is None


class TestUnheardQuestion:
    """Andrius 2026-08-26: the agent must never believe it asked a question
    the caller could not hear — an unheard '?' rolls the ask back and the
    narrator reacts + re-asks."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 1},
        }
        agent.state.messages.append({"role": "assistant", "content": "irrelevant"})
        return agent

    def test_unheard_question_rolls_the_ask_back(self, db_connection):
        agent = self._agent()
        agent.state.last_question = "Ar dega bent viena lemputė?"
        agent._evidence_last_ask_key = "lights"
        agent._evidence_asks = {"lights": 1}
        agent.apply_delivery(["Gerai, kad radote.", "Ar dega bent viena lemputė?"], 1)
        assert agent.state.last_question is None
        assert agent._evidence_last_ask_key is None
        assert agent._evidence_asks["lights"] == 0
        assert agent.state.resolution["presented"]["dr_lights"] == 0
        assert agent._unheard_question == "Ar dega bent viena lemputė?"
        assert agent._undelivered_tail is None  # superseded by the strong note
        block = agent._state_facts_block() or ""
        assert "KLAUSIMAS NEIŠĖJO" in block and "lemputė" in block
        assert "KLAUSIMAS NEIŠĖJO" not in (agent._state_facts_block() or "")

    def test_heard_question_keeps_the_ask(self, db_connection):
        agent = self._agent()
        agent.state.last_question = "Ar dega bent viena lemputė?"
        agent._evidence_last_ask_key = "lights"
        agent._evidence_asks = {"lights": 1}
        agent.apply_delivery(["Ar dega bent viena lemputė?", "Tai parodys, ar gauna srovę."], 1)
        assert agent.state.last_question == "Ar dega bent viena lemputė?"
        assert agent._evidence_last_ask_key == "lights"
        assert agent._unheard_question is None
        assert agent._undelivered_tail  # the plain advisory note stands


class TestW2QuietAnalyst:
    """W2: background advisory notes — wording only, one-shot, off-switch."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.problem_type = "internet_down"
        agent.state.customer_id = "CUST009"
        agent.state.messages.append({"role": "user", "content": "neveikia internetas"})
        return agent

    def test_notes_parsed_filtered_and_consumed_once(self, db_connection, monkeypatch):
        import src.services.llm.client as llm

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
        run_analyst(agent)
        assert agent._analyst_notes == [
            "klientas jau pasake, kada dingo",
            "faktas priestarauja tam, ka klientas kartoja",
        ]
        block = agent._state_facts_block() or ""
        assert "TYLIOJO ANALITIKO" in block and "paprasykite" not in block
        assert "TYLIOJO ANALITIKO" not in (agent._state_facts_block() or "")

    def test_off_switch_and_ok_reply(self, db_connection, monkeypatch):
        import src.services.llm.client as llm
        from agent.analyst import run_analyst

        calls = []
        monkeypatch.setattr(llm, "llm_completion", lambda **k: calls.append(1) or "OK")
        monkeypatch.setenv("ANALYST", "off")
        agent = self._agent()
        run_analyst(agent)
        assert calls == [] and agent._analyst_notes is None
        monkeypatch.setenv("ANALYST", "on")
        run_analyst(agent)
        assert calls == [1] and agent._analyst_notes is None  # OK -> no notes
