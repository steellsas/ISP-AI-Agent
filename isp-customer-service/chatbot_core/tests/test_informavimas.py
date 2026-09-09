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
