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
    """№2/№5 PERDIRBTA (gyvi T-5/T-6, 2026-09-04): pakopa — pasiūlymas, ne
    spąstai; tikslinimas nėra bandymai; kodo režimas praleidžia turinį."""

    def test_extract_account_code_forms(self):
        from agent.identification_flow import _extract_account_code

        assert _extract_account_code("Mano kodas AB-10104") == "AB-10104"
        assert _extract_account_code("ab 10104") == "AB-10104"
        assert _extract_account_code("10104") == "AB-10104"
        assert _extract_account_code("Vilniaus g. 29") is None  # adresas ne kodas
        assert _extract_account_code("nežinau") is None

    def test_code_heard_anytime_without_mode(self, db_connection):
        """Kodas girdimas VISADA — klientas gali jį pasakyti nelaukiamas."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._identification_scripted_reply("Adreso nežinau, bet turiu abonento kodą AB-10104")
        assert agent.state.phone_candidate
        assert agent.state.phone_candidate["customer_id"] == "CUST104"
        assert agent.state.customer_id is None  # adresas SIŪLOMAS, ne prisiimamas

    def test_empty_turns_warn_then_close_no_location(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True  # adreso klausimas jau nuskambėjo
        r1 = agent._identification_scripted_reply("Nežinau adreso")
        assert not agent.state.case_closed
        r2 = agent._identification_scripted_reply("Negaliu pasakyti")
        assert r2 and "negalėsiu" in r2  # PERSPĖJIMAS (su kodo užuomina)
        agent._identification_scripted_reply("Na nežinau")
        r4 = agent._identification_scripted_reply("Nieko nesakysiu")
        assert agent.state.case_closed and r4 and "nenustačius" in r4
        assert agent.state.ticket_id is None

    def test_unrecognized_address_offers_code(self, db_connection):
        """Turinys yra, bet registras jo visai neatpažįsta — po 2 siūlom kodą."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._identification_scripted_reply("Kosmonautų alėja 7")
        r = agent._identification_scripted_reply("Sakau — Kosmonautų alėja septyni")
        assert r and "abonento kodą" in r
        assert agent._awaiting_account_code is True

    def test_code_mode_passes_content_through(self, db_connection):
        """KURTUMO fix: adresas/pavardė kodo režime praleidžiami į normalią
        eigą, o ne atsimuša į „kodas atrodo taip"."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        from agent.identification_flow import _account_code_rung

        handled, reply = _account_code_rung(agent, agent.state, "Petraitis, pasižiūrėkit pavardę")
        assert handled is False and reply is None  # praleista — agentas klauso
        handled, reply = _account_code_rung(agent, agent.state, "Ginkūnai, Žeimių gatvė 12")
        assert handled is False
        assert agent._awaiting_account_code is False  # režimas tyliai užgeso

    def test_explicit_no_code_closes(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        r = agent._identification_scripted_reply("Neturiu jokio kodo")
        assert agent.state.case_closed and r and "abonentams" in r

    def test_city_not_served_is_instant(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        r = agent._identification_scripted_reply("Vilnius, Gedimino prospektas 1")
        assert r and "Šiaulių mieste ir rajone" in r
        assert not agent.state.case_closed
        assert getattr(agent, "_addr_empty_turns", 0) == 0  # ne bandymas

    def test_clarifying_turns_never_count(self, db_connection):
        """Gyva T-6: pavardės tikslinimas skaitiklių neliečia."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._last_agent_question = lambda: "Kokia pavardė, kad galėčiau patvirtinti sutartį?"
        from agent.identification_flow import _account_code_rung

        for txt in ("Tetraitos", "Petraitis", "Pet raitis sakau"):
            handled, reply = _account_code_rung(agent, agent.state, txt)
            assert handled is False and reply is None
        assert getattr(agent, "_addr_empty_turns", 0) == 0


class TestCitySuggestionWiring:
    """Gyva T-5: „Žeimių g. yra Ginkūnuose" + kliento „taip" → miesto slotas
    persijungia, paieška vyksta ten (tikslinimas nėra bandymai)."""

    def test_confirmation_moves_the_city_slot(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._addr_city_suggestion = "Ginkūnai"
        agent._prefill_slots_from_text("Taip, Ginkūnuose")
        assert agent.state.profile.city.value == "Ginkūnai"
        assert agent._addr_city_suggestion is None

    def test_bare_yes_also_moves(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._addr_city_suggestion = "Ginkūnai"
        agent._prefill_slots_from_text("Taip taip")
        assert agent.state.profile.city.value == "Ginkūnai"

    def test_other_answer_keeps_suggestion_open(self, db_connection):
        agent = _agent()
        agent._addr_city_suggestion = "Ginkūnai"
        agent._prefill_slots_from_text("Palaukite, pasižiūrėsiu dokumentuose")
        assert agent.state.profile.city.value is None
        assert agent._addr_city_suggestion == "Ginkūnai"


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
