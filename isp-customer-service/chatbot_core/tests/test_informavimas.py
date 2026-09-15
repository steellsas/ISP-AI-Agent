"""
Informavimo paketai (uždarymo banga, Andrius 2026-09-08): inform verdiktų
kalba iš knowledge/informavimas.yaml — skolos detalės (suma, mėnesiai,
paskutinis mokėjimas) iš invoices lentelės; sakinys be duomenų IŠMETAMAS,
be jokių — fallback. „Pokalbis visuomet baigiasi aiškumu."
"""


def _agent():
    from tests.calls import make_agent

    a = make_agent("+37060020101")
    a.state.identity.customer_id = "CUST101"
    a.state.identity.customer_address = "Šiauliai, Tilžės g. 60-3"
    a.state.intake.problem_type = "internet_down"
    return a


class TestBillingDebtSignal:
    def test_billing_status_carries_debt_details(self, db_connection):
        from agent.tools import get_db
        from crm_mcp.tools.customer_lookup import get_billing_status

        b = get_billing_status(get_db(), "CUST101")
        assert b["success"] and b["suspended"]
        assert b["debt"] == {
            "amount": 49.98,
            "months": ["2026-07", "2026-08"],
            "last_payment": "2026-06-05",
        }

    def test_no_debt_for_paid_customer(self, db_connection):
        from agent.tools import get_db
        from crm_mcp.tools.customer_lookup import get_billing_status

        b = get_billing_status(get_db(), "CUST112")
        assert b["success"] and b["debt"] is None


class TestInformTemplates:
    def test_billing_template_speaks_details(self, db_connection):
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis.verdicts["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        t = inform_text(agent.state, agent.runtime, "billing_suspended")
        assert t and "49 eurai 98 centai" in t
        assert "liepą ir rugpjūtį" in t
        assert "birželio 5 d." in t
        assert "įsijungs automatiškai" in t  # kada atsistatys — aiškumo dalis

    def test_missing_data_drops_sentences_no_lies(self, db_connection):
        """Nėra paskutinio mokėjimo — TAS sakinys išmetamas, kiti lieka."""
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis.verdicts["network"] = {
            "reason": "billing_suspended",
            "signals": {"billing_debt": {"amount": 24.99, "months": ["2026-08"]}},
        }
        t = inform_text(agent.state, agent.runtime, "billing_suspended")
        assert t and "24 eurai 99 centai" in t and "rugpjūtį" in t
        assert "mokėjimas" not in t  # be duomens — be sakinio

    def test_no_data_falls_back(self, db_connection):
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis.verdicts["network"] = {"reason": "billing_suspended", "signals": {}}
        t = inform_text(agent.state, agent.runtime, "billing_suspended")
        assert t and "Apmokėjus sąskaitą" in t  # fallback, ne tuščios skylės

    def test_unknown_reason_returns_none(self, db_connection):
        from agent.informavimas import inform_text

        agent = _agent()
        assert inform_text(agent.state, agent.runtime, "router_hung") is None
        assert inform_text(agent.state, agent.runtime, None) is None

    def test_eur_forms(self):
        from agent.contract.locale import lang

        assert lang().money(1.0) == "1 euras"
        assert lang().money(24.99) == "24 eurai 99 centai"
        assert lang().money(10.01) == "10 eurų 1 centas"


class TestWrapUpHearing:
    """Blokas 2: po „Ar dar kuo padėti?" turinys ATSAKOMAS, ne nuryjamas su
    goodbye; darkyti atsisveikinimai nebekilpuoja (riba 2 turn'ai)."""

    def _informed(self):
        agent = _agent()
        agent.state.identity.caller_name = "Tomas"
        agent.state.diagnosis.news_delivered = True
        agent.state.identity.result_pending = False
        return agent

    def test_payment_claim_is_heard(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed()
        r = identification_scripted_reply(
            agent.state, agent.runtime, "Tai aš vakar sumokėjau sąskaitą"
        )
        assert r is None  # LLM atsako (wants_more), ne goodbye
        assert not agent.state.closing.case_closed

    def test_name_statement_gets_reaction_not_goodbye(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed()
        agent.state.identity.caller_name = None
        r = identification_scripted_reply(agent.state, agent.runtime, "Vilma")
        assert r is None  # naratorius reaguoja su direktyva
        assert agent.state.closing.wrap_react_note is True
        assert not agent.state.closing.case_closed

    def test_farewell_closes_immediately(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed()
        r = identification_scripted_reply(agent.state, agent.runtime, "Ačiū, viso gero")
        assert agent.state.closing.case_closed and r and "Geros dienos" in r

    def test_content_turns_capped_then_close(self, db_connection):
        """Darkytas atsisveikinimas („Nusigaro") — po 2 reakcijų uždaroma."""
        from agent.identification_flow import identification_scripted_reply

        agent = self._informed()
        assert identification_scripted_reply(agent.state, agent.runtime, "Nusigaro") is None
        assert identification_scripted_reply(agent.state, agent.runtime, "Nusigaro visai") is None
        r = identification_scripted_reply(agent.state, agent.runtime, "Nusigaro vėl")
        assert agent.state.closing.case_closed and r and "Geros dienos" in r


class TestTicketCallback:
    """P5 (gyva 2026-09-07): „paskambinsiu vėliau" TIKETO dialogo viduryje —
    callback noras, ne kontaktų atsakymas; šiltas uždarymas be tiketo."""

    def test_callback_wish_mid_ticket_closes_warm(self, db_connection):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import pre_turn_guards
        from agent.resolution import get_strategy
        from agent.ticket_flow import begin_ticket_dialogue, ticket_stage_reply

        agent = _agent()
        agent.state.identity.caller_name = "Tomas"
        agent.state.resolution.procedure = {"verdict": "unclear_fault", "step": "escalate"}
        begin_ticket_dialogue(
            agent.state, agent.runtime, get_strategy("unclear_fault").by_role("escalate")
        )
        ticket_stage_reply(agent.state, agent.runtime)  # numerio klausimas išėjo
        pre_turn_guards(agent.state, agent.runtime, "Gerai, aš paskambinsiu vėliau pats")
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert agent.state.ticket.ticket_id is None
        assert agent.state.ticket.stage is None
        r = identification_scripted_reply(
            agent.state, agent.runtime, "Gerai, aš paskambinsiu vėliau pats"
        )
        assert r and "paskambinkite" in r  # callback_goodbye

    def test_normal_hours_answer_still_captured(self, db_connection):
        from agent.perception_flow import pre_turn_guards
        from agent.resolution import get_strategy
        from agent.ticket_flow import begin_ticket_dialogue, ticket_stage_reply

        agent = _agent()
        agent.state.resolution.procedure = {"verdict": "unclear_fault", "step": "escalate"}
        begin_ticket_dialogue(
            agent.state, agent.runtime, get_strategy("unclear_fault").by_role("escalate")
        )
        ticket_stage_reply(agent.state, agent.runtime)
        pre_turn_guards(agent.state, agent.runtime, "Taip, tiks")
        ticket_stage_reply(agent.state, agent.runtime)
        pre_turn_guards(
            agent.state, agent.runtime, "Skambinkite po 17 valandos"
        )  # JŪS skambinkite — ne callback
        assert not agent.state.closing.case_closed
        assert agent.state.ticket.contact_hours and "17" in agent.state.ticket.contact_hours


class TestDebtSignalsReachState:
    """Gyva 2026-09-09: signals guli payload'o VIRŠUJE, ne verdict'e — state
    gaudavo signals=None ir šablonas krito į fallback („nemato skolos")."""

    def test_diagnose_observation_stores_toplevel_signals(self, db_connection):
        import json

        from agent.narrator_flow import update_state_from_observation

        agent = _agent()
        payload = {
            "success": True,
            "verdict": {
                "side": "provider",
                "group": "B1",
                "action": "inform",
                "reason": "billing_suspended",
            },
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        update_state_from_observation(
            agent.state, agent.runtime, "diagnose_connection", json.dumps(payload)
        )
        sig = agent.state.diagnosis.verdicts["network"]["signals"]
        assert sig and sig["billing_debt"]["amount"] == 49.98
        from agent.informavimas import inform_text

        t = inform_text(agent.state, agent.runtime, "billing_suspended")
        assert t and "49 eurai 98 centai" in t

    def test_facts_block_carries_debt_for_questions(self, db_connection):
        """„Kokia skola?" — naratorius gauna skaičius faktuose, ne „nematau"."""
        from agent.narrator_flow import state_facts_block

        agent = _agent()
        agent.state.diagnosis.verdicts["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        facts = state_facts_block(agent.state, agent.runtime)
        assert facts and "SKOLOS FAKTAI" in facts
        assert "49 eurai 98 centai" in facts and "liepą ir rugpjūtį" in facts


class TestCannotNowHearing:
    """N1-N3 (gyva 2026-09-09): klientui teko 3x kartoti „negaliu" — clarify
    atsakymas dabar girdimas, safety klausimo registro niekas neperrašo,
    „kai grįšiu" = cannot_now."""

    def _solving(self):
        agent = _agent()
        agent.state.identity.customer_id = "CUST112"
        agent.state.identity.caller_name = "Paulius"
        agent.state.resolution.procedure = {"verdict": "unclear_fault", "step": "escalate"}
        return agent

    def test_rambling_cannot_answer_offers_not_resumes(self, db_connection):
        """N2: neaiškus atsakymas į „ar negalite dabar?" = patvirtinimas."""
        from agent.identification_flow import identification_scripted_reply

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "asked"
        r = identification_scripted_reply(agent.state, agent.runtime, "Negaliu, nes esu nenuose")
        assert r and "užregistruoti" in r  # pasiūlymas, ne resume

    def test_callback_in_clarify_answer_closes_warm(self, db_connection):
        """N2b: „Aš Jums perskambinsiu" clarify atsakyme — iškart callback."""
        from agent.identification_flow import identification_scripted_reply

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "asked"
        r = identification_scripted_reply(
            agent.state, agent.runtime, "Negaliu, aš Jums perskambinsiu"
        )
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert r and "paskambinkite" in r

    def test_clear_resume_still_resumes(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "asked"
        r = identification_scripted_reply(
            agent.state, agent.runtime, "Ne ne, galiu, jau radau routerį"
        )
        assert r is None and agent.state.dialog.cannot_now_state is None
        assert not agent.state.closing.case_closed

    def test_kai_grisiu_is_cannot_now(self, db_connection):
        """N3: „Kai grįšiu, namo padarysiu" — ne laukimas, o cannot_now."""
        from agent.resolution import detect_cannot_now

        assert detect_cannot_now("Kai grįšiu, namo padarysiu") is True
        assert detect_cannot_now("Negaliu, nes esu ne mieste") is True

    def test_safety_question_survives_step_presentation(self, db_connection):
        """N1: clarify klausimo registro įrašo mark_step_presented neperrašo."""
        from agent.dialog_registry import active, register
        from agent.narrator_flow import mark_step_presented

        agent = self._solving()
        register(agent.state, agent.runtime, "safety", "cannot_now_clarify")
        agent.state.resolution.procedure["asked"] = False
        mark_step_presented(agent.state, agent.runtime)
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "safety" and q.key == "cannot_now_clarify"

    def test_double_dot_collapsed(self, db_connection):
        """N4: „birželio 5 d.." → vienas taškas."""
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis.verdicts["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        t = inform_text(agent.state, agent.runtime, "billing_suspended")
        assert t and "d.." not in t and "birželio 5 d." in t


class TestHomeworkFinale:
    """F1-F3 (gyva 2026-09-09): homework sutikimas su „viso gero" nebegauna
    „ar tikrai norite baigti?", „perskambinsiu" uždaro callback, o ragelio
    padėjimas homework žingsnyje NEregistruoja tiketo."""

    def _at_homework(self):
        agent = _agent()
        agent.state.identity.customer_id = "CUST112"
        agent.state.identity.caller_name = "Paulius"
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "rh_homework",
            "asked": True,
            "solution_synced": True,
        }
        from agent.dialog_registry import register

        register(agent.state, agent.runtime, "walker", "step:rh_homework")
        return agent

    def test_farewell_consent_routes_to_callback(self, db_connection):
        """F1+F2: „Gerai, sutariam, viso gero" = sutikimas → callback, be
        end-confirm rato."""
        from agent.perception_flow import pre_turn_guards
        from agent.walker_flow import advance_resolution

        agent = self._at_homework()
        pre_turn_guards(agent.state, agent.runtime, "Gerai, sutariam, viso gero.")
        assert agent.state.dialog.end_confirm_pending is False  # end-confirm nekilo
        advance_resolution(agent.state, agent.runtime, "Gerai, sutariam, viso gero.")
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert agent.state.ticket.ticket_id is None

    def test_callback_promise_routes_to_callback(self, db_connection):
        from agent.walker_flow import advance_resolution

        agent = self._at_homework()
        advance_resolution(
            agent.state, agent.runtime, "Nereikia susitikti, aš perskambinsiu, sakiau."
        )
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"

    def test_ticket_demand_still_wins(self, db_connection):
        from agent.walker_flow import advance_resolution

        agent = self._at_homework()
        advance_resolution(agent.state, agent.runtime, "Gerai, bet registruokite meistrą dabar.")
        assert not (
            agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        )

    def test_hangup_at_homework_closes_callback_no_ticket(self, db_connection):
        """F3: ragelis homework žingsnyje — callback, ne TKT."""
        agent = self._at_homework()
        agent.end_session(outcome="client_closed")
        assert agent.state.closing.closed_reason == "callback"
        assert agent.state.ticket.ticket_id is None


class TestRestoredGarble:
    def test_satsarado_reads_as_restored(self, db_connection):
        """P-B gyva: „interneto satsarado" (STT „atsirado") — restored YES."""
        from agent.resolution import Outcome, detect_restored

        assert detect_restored("Mhm, interneto satsarado") is Outcome.YES
        assert detect_restored("interneto atsarado jau") is Outcome.YES


class TestNodeFaultInform:
    """B3 inform (Andrius 2026-09-11): mazgo/switch gedimas — statinis šablonas
    kalba (be placeholder'ių), variklis pats sukuria tiketą prieš žodžius."""

    def test_static_templates_speak(self, db_connection):
        from agent.informavimas import inform_text

        a = _agent()
        t = inform_text(a.state, a.runtime, "node_fault_unregistered")
        assert t and "nieko daryti nereikia" in t and "informuosime" in t
        assert "užregistravau" in t
        t2 = inform_text(a.state, a.runtime, "switch_unreachable")
        assert t2 and "nieko daryti nereikia" in t2 and "informuosime" in t2

    def test_deferred_result_registers_ticket_and_informs(self, db_connection):
        from agent.identification_flow import identification_scripted_reply

        from tests.calls import make_agent

        a = make_agent("+37060030306")
        a.state.identity.customer_id = "CUST306"
        a.state.identity.customer_address = "Šiauliai, Vilties g. 17-2"
        a.state.intake.problem_type = "internet_down"
        a.state.identity.caller_name = "Lina"
        a.state.identity.result_pending = True
        a.state.diagnosis.verdicts["network"] = {"reason": "node_fault_unregistered", "signals": {}}
        a.state.diagnosis.hypothesis = {
            "cause": "node_fault_unregistered",
            "because": [],
            "status": "testing",
            "settled_by": None,
        }
        r = identification_scripted_reply(a.state, a.runtime, "Lina čia")
        assert r and "meistrai" in r.lower() and "informuosime" in r
        assert "neregistruotas" not in r  # žalias gloss'as nebekalba
        assert a.state.ticket.ticket_id  # „meistrai jau užregistruoti" — tiesa


class TestInformResultComposer:
    def test_deferred_result_uses_template(self, db_connection):
        """Pilnas kelias: diagnozė su skola → atidėtas rezultatas kalba
        šablonu (viena žinia su detalėm), be billing_extra dubliavimo."""
        from agent.identification_flow import identification_scripted_reply

        agent = _agent()
        agent.state.identity.caller_name = "Tomas"
        agent.state.identity.result_pending = True
        agent.state.diagnosis.verdicts["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        r = identification_scripted_reply(agent.state, agent.runtime, "Tomas čia")
        assert r and "49 eurai 98 centai" in r and "liepą ir rugpjūtį" in r
        assert r.count("Apmokėjus") == 1  # šablonas vietoj billing_extra, ne kartu
