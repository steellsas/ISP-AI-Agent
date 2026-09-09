"""
Informavimo paketai (uždarymo banga, Andrius 2026-09-08): inform verdiktų
kalba iš knowledge/informavimas.yaml — skolos detalės (suma, mėnesiai,
paskutinis mokėjimas) iš invoices lentelės; sakinys be duomenų IŠMETAMAS,
be jokių — fallback. „Pokalbis visuomet baigiasi aiškumu."
"""


def _agent():
    from agent.react_agent import ReactAgent

    a = ReactAgent(caller_phone="+37060020101")
    a.state.customer_id = "CUST101"
    a.state.customer_address = "Šiauliai, Tilžės g. 60-3"
    a.state.problem_type = "internet_down"
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
        agent.state.diagnosis["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        t = inform_text(agent, "billing_suspended")
        assert t and "49 eurai 98 centai" in t
        assert "liepą ir rugpjūtį" in t
        assert "birželio 5 d." in t
        assert "įsijungs automatiškai" in t  # kada atsistatys — aiškumo dalis

    def test_missing_data_drops_sentences_no_lies(self, db_connection):
        """Nėra paskutinio mokėjimo — TAS sakinys išmetamas, kiti lieka."""
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis["network"] = {
            "reason": "billing_suspended",
            "signals": {"billing_debt": {"amount": 24.99, "months": ["2026-08"]}},
        }
        t = inform_text(agent, "billing_suspended")
        assert t and "24 eurai 99 centai" in t and "rugpjūtį" in t
        assert "mokėjimas" not in t  # be duomens — be sakinio

    def test_no_data_falls_back(self, db_connection):
        from agent.informavimas import inform_text

        agent = _agent()
        agent.state.diagnosis["network"] = {"reason": "billing_suspended", "signals": {}}
        t = inform_text(agent, "billing_suspended")
        assert t and "Apmokėjus sąskaitą" in t  # fallback, ne tuščios skylės

    def test_unknown_reason_returns_none(self, db_connection):
        from agent.informavimas import inform_text

        assert inform_text(_agent(), "router_hung") is None
        assert inform_text(_agent(), None) is None

    def test_eur_forms(self):
        from agent.informavimas import _eur

        assert _eur(1.0) == "1 euras"
        assert _eur(24.99) == "24 eurai 99 centai"
        assert _eur(10.01) == "10 eurų 1 centas"


class TestWrapUpHearing:
    """Blokas 2: po „Ar dar kuo padėti?" turinys ATSAKOMAS, ne nuryjamas su
    goodbye; darkyti atsisveikinimai nebekilpuoja (riba 2 turn'ai)."""

    def _informed(self):
        agent = _agent()
        agent.state.caller_name = "Tomas"
        agent._news_told = True
        agent._result_pending = False
        return agent

    def test_payment_claim_is_heard(self, db_connection):
        agent = self._informed()
        r = agent._identification_scripted_reply("Tai aš vakar sumokėjau sąskaitą")
        assert r is None  # LLM atsako (wants_more), ne goodbye
        assert not agent.state.case_closed

    def test_name_statement_gets_reaction_not_goodbye(self, db_connection):
        agent = self._informed()
        agent.state.caller_name = None
        r = agent._identification_scripted_reply("Vilma")
        assert r is None  # naratorius reaguoja su direktyva
        assert agent._wrap_react_note is True
        assert not agent.state.case_closed

    def test_farewell_closes_immediately(self, db_connection):
        agent = self._informed()
        r = agent._identification_scripted_reply("Ačiū, viso gero")
        assert agent.state.case_closed and r and "Geros dienos" in r

    def test_content_turns_capped_then_close(self, db_connection):
        """Darkytas atsisveikinimas („Nusigaro") — po 2 reakcijų uždaroma."""
        agent = self._informed()
        assert agent._identification_scripted_reply("Nusigaro") is None
        assert agent._identification_scripted_reply("Nusigaro visai") is None
        r = agent._identification_scripted_reply("Nusigaro vėl")
        assert agent.state.case_closed and r and "Geros dienos" in r


class TestTicketCallback:
    """P5 (gyva 2026-09-07): „paskambinsiu vėliau" TIKETO dialogo viduryje —
    callback noras, ne kontaktų atsakymas; šiltas uždarymas be tiketo."""

    def test_callback_wish_mid_ticket_closes_warm(self, db_connection):
        from agent.resolution import STRATEGIES

        agent = _agent()
        agent.state.caller_name = "Tomas"
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate"}
        agent._begin_ticket_dialogue(STRATEGIES["unclear_fault"].step("escalate"))
        agent._ticket_stage_reply()  # numerio klausimas išėjo
        agent._pre_turn_guards("Gerai, aš paskambinsiu vėliau pats")
        assert agent.state.case_closed and agent.state.closed_reason == "callback"
        assert agent.state.ticket_id is None
        assert agent._ticket_stage is None
        r = agent._identification_scripted_reply("Gerai, aš paskambinsiu vėliau pats")
        assert r and "paskambinkite" in r  # callback_goodbye

    def test_normal_hours_answer_still_captured(self, db_connection):
        from agent.resolution import STRATEGIES

        agent = _agent()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate"}
        agent._begin_ticket_dialogue(STRATEGIES["unclear_fault"].step("escalate"))
        agent._ticket_stage_reply()
        agent._pre_turn_guards("Taip, tiks")
        agent._ticket_stage_reply()
        agent._pre_turn_guards("Skambinkite po 17 valandos")  # JŪS skambinkite — ne callback
        assert not agent.state.case_closed
        assert agent.state.contact_hours and "17" in agent.state.contact_hours


class TestRestoredGarble:
    def test_satsarado_reads_as_restored(self, db_connection):
        """P-B gyva: „interneto satsarado" (STT „atsirado") — restored YES."""
        from agent.resolution import Outcome, detect_restored

        assert detect_restored("Mhm, interneto satsarado") is Outcome.YES
        assert detect_restored("interneto atsarado jau") is Outcome.YES


class TestInformResultComposer:
    def test_deferred_result_uses_template(self, db_connection):
        """Pilnas kelias: diagnozė su skola → atidėtas rezultatas kalba
        šablonu (viena žinia su detalėm), be billing_extra dubliavimo."""
        agent = _agent()
        agent.state.caller_name = "Tomas"
        agent._result_pending = True
        agent.state.diagnosis["network"] = {
            "reason": "billing_suspended",
            "signals": {
                "billing_debt": {
                    "amount": 49.98,
                    "months": ["2026-07", "2026-08"],
                    "last_payment": "2026-06-05",
                }
            },
        }
        r = agent._identification_scripted_reply("Tomas čia")
        assert r and "49 eurai 98 centai" in r and "liepą ir rugpjūtį" in r
        assert r.count("Apmokėjus") == 1  # šablonas vietoj billing_extra, ne kartu
