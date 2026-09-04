"""
Identifikacijos etalono taisyklės (Andrius 2026-09-03, docs/IDENT_TESTAI.md):
№1 butas pagal DB (resolveris jau moka — regresijos sargas), №2/№5 abonento
kodo pakopa + „pagalba tik abonentams", №3 adreso keitimas tik su
patvirtinimu, №4 savininko vardo patikra be DB vardo garsinimo.
"""


def _agent(phone="unknown"):
    from agent.react_agent import ReactAgent

    return ReactAgent(caller_phone=phone)


class TestApartmentByRegistry:
    """№1: buto klausiama TIK kai name >1 sutartis (resolverio mechanika)."""

    def test_single_contract_resolves_without_apartment(self, db_connection):
        import json

        from agent.tools import execute_tool

        r = json.loads(
            execute_tool(
                "resolve_address",
                {"street": "Vilniaus g.", "house_number": "29", "city": "Šiauliai"},
            )
        )
        assert r["success"] is True and r["customer_id"] == "CUST009"

    def test_multi_contract_requires_apartment(self, db_connection):
        import json

        from agent.tools import execute_tool

        r = json.loads(
            execute_tool(
                "resolve_address",
                {"street": "Tilžės g.", "house_number": "60", "city": "Šiauliai"},
            )
        )
        assert r["success"] is False
        assert r["resolution"]["apartment"]["status"] == "required"
        assert "buto" in (r.get("hint") or "")


class TestAccountCodeRung:
    """№2/№5: adresas neaiškėja → abonento kodas → radus siūlomas adresas;
    neradus — „tik abonentams" ir uždarymas be tiketo."""

    def test_extract_account_code_forms(self):
        from agent.identification_flow import _extract_account_code

        assert _extract_account_code("Mano kodas AB-10104") == "AB-10104"
        assert _extract_account_code("ab 10104") == "AB-10104"
        assert _extract_account_code("10104") == "AB-10104"
        assert _extract_account_code("Vilniaus g. 29") is None  # adresas ne kodas
        assert _extract_account_code("nežinau") is None

    def _worn_out(self, agent, monkeypatch=None):
        agent.state.problem_type = "internet_down"
        replies = []
        for t in ("Nežinau adreso", "Negaliu pasakyti", "Tikrai nežinau", "Na nežinau"):
            replies.append(agent._identification_scripted_reply(t))
        return replies

    def test_rung_opens_after_limit_and_finds_customer(self, db_connection):
        agent = _agent()
        replies = self._worn_out(agent)
        assert replies[-1] and "abonento kodą" in replies[-1]  # pakopa atsidarė
        assert agent._awaiting_account_code is True
        reply = agent._identification_scripted_reply("Mano abonento kodas AB-10104")
        assert agent.state.phone_candidate
        assert agent.state.phone_candidate["customer_id"] == "CUST104"
        # adresas SIŪLOMAS balsu (address_offer kelias), ne prisiimamas
        assert agent.state.customer_id is None

    def test_unreadable_code_retries_then_closes(self, db_connection):
        agent = _agent()
        self._worn_out(agent)
        r1 = agent._identification_scripted_reply("O kur man jį rasti?")
        assert r1 and "penki skaitmenys" in r1  # retry with the WHERE hint
        r2 = agent._identification_scripted_reply("Nerandu niekur")
        assert agent.state.case_closed
        assert r2 and "abonentams" in r2
        assert agent.state.ticket_id is None

    def test_explicit_no_code_closes_immediately(self, db_connection):
        """AIŠKUS „neturiu" — atsakymas gautas, kartoti nebėra ko."""
        agent = _agent()
        self._worn_out(agent)
        r = agent._identification_scripted_reply("Neturiu jokio kodo")
        assert agent.state.case_closed
        assert r and "abonentams" in r


class TestReopenConfirmation:
    """№3: adreso keitimas po identifikacijos — tik su patvirtinimu."""

    def _identified(self):
        agent = _agent(phone="+37060020112")
        agent.state.customer_id = "CUST112"
        agent.state.customer_address = "Šiauliai, Vilniaus g. 33-2"
        agent.state.problem_type = "internet_down"
        return agent

    def test_correction_asks_before_reopening(self, db_connection):
        agent = self._identified()
        agent._reopen_confirm_pending = "iš tikrųjų skambinu dėl Tilžės g. 60"
        agent._reopen_confirm_asked = False
        reply = agent._identification_scripted_reply("iš tikrųjų skambinu dėl Tilžės g. 60")
        assert reply and "tikrai" in reply and "Vilniaus g. 33-2" in reply
        assert agent.state.customer_id == "CUST112"  # dar NEperjungta

    def test_yes_reopens_no_keeps(self, db_connection):
        agent = self._identified()
        agent._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent._reopen_confirm_asked = True
        agent._identification_scripted_reply("Taip, dėl kito")
        assert agent.state.customer_id is None  # atidaryta iš naujo

        agent2 = self._identified()
        agent2._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent2._reopen_confirm_asked = True
        agent2._identification_scripted_reply("Ne ne, likim prie šito")
        assert agent2.state.customer_id == "CUST112"  # liko


class TestHolderNameCheck:
    """№4: sakosi savininkas kitu vardu → patikslinimas BE DB vardo."""

    def test_fuzzy_match_tolerates_stt(self, db_connection):
        from agent.perception_flow import _holder_name_matches

        agent = _agent()
        agent.state.customer_name = "Andrius Pilienius"
        assert _holder_name_matches(agent, "Andrijus") is True  # STT darkymas
        agent.state.customer_name = "Giedrius Giedraitis"
        assert _holder_name_matches(agent, "Petras") is False
        agent.state.customer_name = None
        assert _holder_name_matches(agent, "Bet kas") is True  # nėra su kuo lyginti

    def test_mismatch_asks_scripted_and_nameless(self, db_connection):
        agent = _agent()
        agent.state.customer_id = "CUST009"
        agent.state.customer_name = "Giedrius Giedraitis"
        agent.state.caller_name = "Petras"
        agent._holder_clarify_open = True
        agent._holder_clarify_asked = False
        reply = agent._identification_scripted_reply("Petras, aš savininkas")
        assert reply and "kitu vardu" in reply  # scripted, deterministinis
        assert "Giedri" not in reply  # DB vardas NIEKADA negarsinamas

    def test_clarify_answer_updates_relation(self, db_connection):
        agent = _agent()
        agent.state.customer_id = "CUST009"
        agent.state.caller_name = "Petras"
        agent.state.caller_relation = "holder"
        agent._holder_clarify_open = True
        agent._holder_clarify_asked = True  # klausimas jau nuskambėjo
        agent._prefill_slots_from_text("Žmonos vardu sudaryta sutartis")
        assert agent.state.caller_relation != "holder"
