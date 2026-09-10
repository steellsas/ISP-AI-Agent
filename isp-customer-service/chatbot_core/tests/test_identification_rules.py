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
        """Turinys yra, bet registras jo visai neatpažįsta — po 2 siūlom kodą
        (rev.2 2026-09-10: automatinių raidžių nebėra, fuzzy — pagrindinis)."""
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
        # Atsakymą skaito pre_turn_guards (A-2: kad solveris/walker'is jo
        # nesuvartotų) — testas kviečia gyvą kelią.
        agent = self._identified()
        agent._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent._reopen_confirm_asked = True
        agent._pre_turn_guards("Taip, dėl kito")
        assert agent.state.customer_id is None  # atidaryta iš naujo

        agent2 = self._identified()
        agent2._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent2._reopen_confirm_asked = True
        agent2._pre_turn_guards("Ne ne, likim prie šito")
        assert agent2.state.customer_id == "CUST112"  # liko
        assert agent2._reopen_confirm_pending is None

    def test_unclear_answer_reasks_not_burns(self, db_connection):
        """A-2 gyva yda: neaiškus atsakymas klausimo nebesudegina — vienas
        pakartojimas, o walker'is tą turn'ą laikomas (hold)."""
        agent = self._identified()
        agent._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent._reopen_confirm_asked = True
        agent._reopen_confirm_asks = 1
        agent._pre_turn_guards("Nu kaip čia dabar pasakyt")
        assert agent._reopen_confirm_pending is not None  # klausimas gyvas
        assert agent._resume_hold is True  # walker'is nesuvartos turn'o
        r = agent._identification_scripted_reply("Nu kaip čia dabar pasakyt")
        assert r and "KITO adreso" in r  # pakartojimas
        # Antras neaiškus — nurašom (liekam prie esamo), be amžino ciklo.
        agent._pre_turn_guards("Mhm chm")
        assert agent._reopen_confirm_pending is None
        assert agent.state.customer_id == "CUST112"

    def test_address_question_is_answered(self, db_connection):
        """A-2b: „dėl kokio adreso mes bendraujame?" — agentas SAKO adresą
        (patvirtintas adresas nėra paslaptis; taip klientas pagauna klaidą)."""
        agent = self._identified()
        r = agent._identification_scripted_reply("Dėl kokio adreso mes dabar bendraujame?")
        assert r and "Vilniaus g. 33-2" in r

    def test_confirmed_reopen_drops_bg_and_continues_ident(self, db_connection):
        """A-2R gyva yda: po „taip" foninis telemetrijos skaitymas atstatydavo
        senos sąskaitos diagnozę, o identifikacija nesitęsė — dabar bg išmetamas
        ir variklis IŠ KARTO bando naują adresą (Tilžės 60 → buto klausimas)."""
        agent = self._identified()
        agent.state.diagnosis["network"] = {"group": "B6", "reason": "router_hung"}
        agent._bg_diagnosis = '{"success": true}'
        agent.state.phone_candidate = {"customer_id": "CUST112", "street": "Vilniaus g."}
        agent._reopen_confirm_pending = "mano adresas yra Tilžės gatvė 60"
        agent._reopen_confirm_asked = True
        agent._pre_turn_guards("Taip taip, dėl KITO adreso skambinu")
        assert agent.state.customer_id is None  # sena tapatybė numesta
        assert agent._bg_diagnosis is None  # telemetrija išmesta kartu
        assert agent.state.diagnosis == {}  # senų išvadų nebėra
        assert agent.state.phone_candidate is None  # senas adresas nebesiūlomas
        assert agent.state.problem_type == "internet_down"  # problema LIEKA
        # Tilžės 60 pabandyta iš karto → „koks butas?" nota reply sluoksniui.
        assert agent._addr_diag_note or agent._db_address_note

    def test_garbled_answer_does_not_stomp_good_pending_slots(self, db_connection):
        """P1 gyva: pending davė Tilžės 60 (conf 1.0), atsakymo darkymas
        „Tildžiai 660-3" jo nebeperrašo — resolve eina su 60."""
        agent = self._identified()
        agent._reopen_confirm_pending = "mano adresas yra Tilžės gatvė 60"
        agent._reopen_confirm_asked = True
        agent._pre_turn_guards("Taip, dėl KITO adreso. Dėl Tildžiai 660-3.")
        assert agent.state.profile.house.value == "60"  # ne 660

    def test_address_echo_question_freezes_counters(self, db_connection):
        """P3 gyva: „Taip." į adreso echo klausimą (net LLM'o žodžiais) —
        tikslinimas, ne tuščias turn'as."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._last_agent_question = lambda: (
            "Taigi, adresas yra Šiauliai, Tilžės g. 60, butas 3, taip?"
        )
        from agent.identification_flow import _account_code_rung

        handled, reply = _account_code_rung(agent, agent.state, "Taip.")
        assert handled is False and reply is None
        assert getattr(agent, "_addr_empty_turns", 0) == 0

    def test_confirmed_reopen_commits_single_contract_address(self, db_connection):
        """Naujas adresas be butų (Vilniaus g. 29) — po „taip" identifikacija
        įvyksta TĄ PATĮ turn'ą, be papildomų klausimų."""
        agent = self._identified()
        agent._reopen_confirm_pending = "skambinu dėl Vilniaus gatvės 29"
        agent._reopen_confirm_asked = True
        agent._pre_turn_guards("Taip")
        assert agent.state.customer_id == "CUST009"  # nauja sutartis prisirišo

    def test_address_question_mid_ident_names_heard_address(self, db_connection):
        """A-2R-b gyva: „kokiu adresu bendraujam?" PO reopen (klientas numestas,
        adresas slotuose) — agentas sako, KĄ tikslina, ne improvizuoja."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        from agent.slots import SlotStatus

        agent.state.profile.street.propose("Tilžės g.", 1.0, SlotStatus.HEARD)
        agent.state.profile.house.propose("60", 1.0, SlotStatus.HEARD)
        r = agent._identification_scripted_reply("Tai kokiu adresu dabar bendraujam, tikrinam?")
        assert r and "Tilžės g. 60" in r and "dėl šio adreso" in r

    def test_address_question_mid_ident_without_slots(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        r = agent._identification_scripted_reply("Galite pasakyti tikslų adresą, kur tikrinat?")
        assert r and "nenustat" in r

    def test_yes_to_heard_address_commits_from_slots(self, db_connection):
        """„Taip" į „ar skambinate dėl šio adreso?" be telefono kandidato —
        variklis riša iš slotų (vienos sutarties adresas prisiriša iš karto)."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        from agent.slots import SlotStatus

        agent.state.profile.street.propose("Vilniaus g.", 1.0, SlotStatus.HEARD)
        agent.state.profile.house.propose("29", 1.0, SlotStatus.HEARD)
        agent.state.messages.append(
            {
                "role": "assistant",
                "content": "Girdėjau adresą Vilniaus g. 29, bet dar nepatvirtinau. Ar skambinate dėl šio adreso?",
            }
        )
        agent._pre_turn_guards("Taip taip.")
        assert agent.state.customer_id == "CUST009"

    def test_bg_diagnosis_never_applies_without_customer(self, db_connection):
        agent = _agent()
        agent._bg_diagnosis = '{"success": true}'
        agent._apply_bg_diagnosis()
        assert agent._bg_diagnosis is None
        assert agent.state.diagnosis == {}


class TestQuestionRegistry:
    """B banga, žingsnis 1 (shadow): registras atspindi saugiklių klausimus —
    kas klausė, kelintą kartą; skaitytuvai jį valo."""

    def _identified(self):
        agent = _agent(phone="+37060020112")
        agent.state.customer_id = "CUST112"
        agent.state.customer_address = "Šiauliai, Vilniaus g. 33-2"
        agent.state.problem_type = "internet_down"
        return agent

    def test_reopen_lifecycle_ask_reask_close(self, db_connection):
        from agent.dialog_registry import active

        agent = self._identified()
        agent._reopen_confirm_pending = "dėl Tilžės g. 60"
        agent._reopen_confirm_asked = False
        agent._identification_scripted_reply("dėl Tilžės g. 60")  # ask
        q = active(agent)
        assert q and q.owner == "safety" and q.key == "reopen_confirm" and q.asks == 1
        agent._pre_turn_guards("Nu kaip čia pasakyt")  # unclear → reask
        agent._identification_scripted_reply("Nu kaip čia pasakyt")
        q = active(agent)
        assert q and q.asks == 2  # pakartojimas registruotas
        agent._pre_turn_guards("Mhm chm")  # antras neaiškus → nurašyta
        assert active(agent) is None

    def test_reopen_confirmed_clears(self, db_connection):
        from agent.dialog_registry import active

        agent = self._identified()
        agent._reopen_confirm_pending = "dėl Vilniaus gatvės 29"
        agent._reopen_confirm_asked = False
        agent._identification_scripted_reply("dėl Vilniaus gatvės 29")
        agent._pre_turn_guards("Taip")
        assert active(agent) is None
        assert agent.state.customer_id == "CUST009"

    def test_ticket_question_lifecycle(self, db_connection):
        """B žingsnis 3: tiketo klausimai (numeris → valandos) registre;
        registracija uždaro savininką."""
        from agent.dialog_registry import active
        from agent.resolution import STRATEGIES

        agent = self._identified()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate"}
        agent._begin_ticket_dialogue(STRATEGIES["unclear_fault"].step("escalate"))
        agent._ticket_stage_reply()
        q = active(agent)
        assert q and q.owner == "ticket" and q.key == "ticket_phone"
        agent._pre_turn_guards("Taip, tiks")
        agent._ticket_stage_reply()
        q = active(agent)
        assert q and q.key == "ticket_hours"
        agent._pre_turn_guards("Po 17 valandos")
        agent._finish_ticket_dialogue()
        assert agent.state.ticket_id
        assert active(agent) is None  # dialogas baigtas — registras švarus

    def test_walker_evidence_question_closes_on_fact(self, db_connection):
        """B žingsnis 4: įrodymo klausimas registre užsidaro, kai ateina jo
        rakto faktas (kito rakto faktas jo neliečia)."""
        from agent.dialog_registry import active, register

        agent = self._identified()
        register(agent, "walker", "evidence:lights")
        agent._ingest_client_evidence("Nei viena lemputė nedega")
        assert active(agent) is None
        # kito rakto faktas svetimo klausimo neuždaro
        register(agent, "walker", "evidence:fail_scope")
        agent._ingest_client_evidence("Kabelis įkištas gerai")
        assert active(agent) is not None

    def test_step_presentation_registers(self, db_connection):
        from agent.dialog_registry import active

        agent = self._identified()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate", "asked": False}
        agent._mark_step_presented()
        q = active(agent)
        assert q and q.owner == "walker" and q.key == "step:escalate"
        # Gyva 2026-09-08: end-confirm/wrap-up replikos NE žingsnio klausimas —
        # jos nebekelia asks; uždarytas atvejis valo walker savininką.
        agent._end_confirm_pending = True
        agent._mark_step_presented()
        assert active(agent).asks == 1  # nepakito
        agent._end_confirm_pending = False
        agent.state.case_closed = True
        agent._mark_step_presented()
        assert active(agent) is None  # wrap-up fazė — walker uždarytas

    def test_cannot_now_shield_beats_walker_refuse(self, db_connection):
        """P-D gyva: „nepatogu, nesu namuose" — anksčiau walker'io refuse
        guard'as tą patį turn'ą startavo tiketą; dabar galvos skydas
        registruoja safety klausimą ir walker'is laiko."""
        from agent.dialog_registry import active

        agent = self._identified()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate", "asked": True}
        msg = "Nepatogu man tai daryt, aš nesu namuose dabar."
        agent._pre_turn_guards(msg)
        q = active(agent)
        assert q and q.owner == "safety" and q.key == "cannot_now"
        agent._advance_resolution(msg)
        assert agent._ticket_stage is None  # tiketas NEprasidėjo
        r = agent._identification_scripted_reply(msg)
        assert r and "nepatogu" in r  # laiptelis klausia KAS nepatogu

    def test_ability_yes_routes_to_reboot(self, db_connection):
        """P-C: gebėjimo klausimas — „taip" veda į perkrovimo instrukciją."""
        agent = self._identified()
        agent.state.resolution = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        agent._advance_resolution("Taip, galiu, esu prie routerio")
        assert agent.state.resolution["step"] == "rh_reboot"

    def test_ability_no_routes_to_homework_then_callback(self, db_connection):
        """P-C: „ne" → namų darbas; sutikimas → callback uždarymas su scripted
        atsisveikinimu, be tiketo."""
        agent = self._identified()
        agent.state.resolution = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        agent._advance_resolution("Ne.")
        assert agent.state.resolution["step"] == "rh_homework"
        agent.state.resolution["asked"] = True
        agent._advance_resolution("Taip, sutinku.")
        assert agent.state.case_closed and agent.state.closed_reason == "callback"
        assert agent.state.ticket_id is None
        r = agent._identification_scripted_reply("Taip, sutinku.")
        assert r and "paskambinkite" in r  # callback_goodbye

    def test_soft_refuse_at_ability_stays_with_pack(self, db_connection):
        """P-C: švelnus „nesu namuose" ability žingsnyje NEeskaluoja į tiketą —
        pack'as pats nuves į homework; aiškus reikalavimas vis tiek laimi."""
        agent = self._identified()
        agent.state.resolution = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        from agent.dialog_registry import register

        register(agent, "walker", "step:rh_ability")
        agent._pre_turn_guards("Nepatogu, nesu namuose dabar")
        # skydas NEkyla (pack'o žingsnis valdo), tiketas NEprasidėjo
        from agent.dialog_registry import active

        q = active(agent)
        assert q and q.key == "step:rh_ability"
        assert agent._ticket_stage is None

    def test_homework_no_escalates_with_honest_reason(self, db_connection):
        agent = self._identified()
        agent.state.resolution = {
            "verdict": "router_hung",
            "step": "rh_homework",
            "asked": True,
            "solution_synced": True,
        }
        agent._advance_resolution("Ne, geriau meistrą registruokim")
        assert agent.state.resolution.get("escalate_reason")
        need = agent._ticket_need()
        assert "nepavyko" in need and "perkrautas" not in need

    def test_ticket_need_honest_on_refusal(self, db_connection):
        """P-E gyva: „routeris perkrautas, bet ryšys neatsistatė" — melas, kai
        veiksmo nebuvo; atsisakymo/negalėjimo eskalacija sako sąžiningai."""
        agent = self._identified()
        agent.state.resolution = {
            "verdict": "router_hung",
            "step": "escalate",
            "escalate_reason": "Klientas negali dabar atlikti veiksmų prie įrenginio.",
        }
        need = agent._ticket_need()
        assert "nepavyko" in need
        assert "perkrautas" not in need and "neatsistatė" not in need

    def test_priority_guard_holds_walker_on_safety_question(self, db_connection):
        """PERJUNGIMAS (P6): kol atviras safety/ident/ticket klausimas, walker'is
        turn'o neskaito kaip savo žingsnio atsakymo."""
        from agent.dialog_registry import active, clear_owner, register

        agent = self._identified()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate", "asked": True}
        register(agent, "safety", "cannot_now_offer")
        agent._advance_resolution("Registruokite meistrą")
        assert agent._ticket_stage is None  # walker'is nepradėjo tiketo — laiko
        assert active(agent) is not None  # klausimas gyvas, jį skaito savininkas
        # Klausimui užsidarius — walker'is vėl skaito normaliai.
        clear_owner(agent, "safety")
        agent._advance_resolution("Registruokite meistrą")
        assert agent._ticket_stage is not None  # dabar tiketo dialogas prasidėjo

    def test_caller_name_closes_on_capture(self, db_connection):
        """Gyva 2026-09-08: vardo klausimas registre kabėjo atviras po atsakymo."""
        from agent.dialog_registry import active, register

        agent = self._identified()
        agent._result_pending = True
        register(agent, "ident", "caller_name")
        agent._pre_turn_guards("Paulius mano vardas")
        assert agent.state.caller_name == "Paulius"
        assert active(agent) is None

    def test_code_echo_offer_registers_as_address_offer(self, db_connection):
        """Gyva 2026-09-08: kodo echo pasiūla apeidavo _address_move ir likdavo
        neregistruota."""
        from agent.dialog_registry import active
        from agent.identification_flow import _account_code_rung

        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        _account_code_rung(agent, agent.state, "AB 10104")
        q = active(agent)
        assert q and q.owner == "ident" and q.key == "address_offer"

    def test_cannot_now_lifecycle(self, db_connection):
        from agent.dialog_registry import active
        from agent.resolution import STRATEGIES

        agent = self._identified()
        agent.state.resolution = {"verdict": "unclear_fault", "step": "escalate"}
        agent._identification_scripted_reply("Ne patogu man dabar")
        q = active(agent)
        assert q and q.key == "cannot_now_clarify"
        agent._identification_scripted_reply("Nesu namie dabar")
        q = active(agent)
        assert q and q.key == "cannot_now_offer"
        r = agent._identification_scripted_reply("Gerai, paskambinsiu vėliau")
        assert agent.state.case_closed and agent.state.closed_reason == "callback"
        assert active(agent) is None
        assert STRATEGIES  # naudota fixture kelio įkėlimui


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


class TestCannotNowLadder:
    """A-banga P1 (gyva #6 2026-09-04: „Ne patogu" ignoruotas): STOP →
    „kas nepatogu?" → registracija / perskambinimas / tęsiam."""

    def _solving(self):
        agent = _agent()
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights"}
        return agent

    def test_cannot_now_asks_what_is_wrong(self, db_connection):
        agent = self._solving()
        r = agent._identification_scripted_reply("Ne patogu")
        assert r and "kas nepatogu" in r
        assert agent._cannot_now_state == "asked"

    def test_confirmed_cannot_offers_paths(self, db_connection):
        agent = self._solving()
        agent._cannot_now_state = "asked"
        r = agent._identification_scripted_reply("Na, aš ne namie dabar")
        assert r and "užregistruoti" in r and "paskambinkite" in r

    def test_callback_choice_closes_politely(self, db_connection):
        agent = self._solving()
        agent._cannot_now_state = "offered"
        r = agent._identification_scripted_reply("Geriau pats perskambinsiu vėliau")
        assert agent.state.case_closed and agent.state.closed_reason == "callback"
        assert r and "paskambinkite" in r
        assert agent.state.ticket_id is None

    def test_ticket_choice_starts_dialogue(self, db_connection):
        agent = self._solving()
        agent._cannot_now_state = "offered"
        agent._identification_scripted_reply("Registruokite meistrą")
        assert agent._ticket_stage == "phone"

    def test_explained_otherwise_resumes(self, db_connection):
        agent = self._solving()
        agent._cannot_now_state = "asked"
        r = agent._identification_scripted_reply("Ne ne, viskas gerai, jau radau routerį")
        assert r is None  # kelias tęsiasi
        assert agent._cannot_now_state is None

    def test_in_flow_negaliu_is_not_a_signal(self, db_connection):
        from agent.resolution import detect_cannot_now

        assert detect_cannot_now("Negaliu prisijungti prie interneto") is False
        assert detect_cannot_now("Negaliu rasti tos dėžutės") is False
        assert detect_cannot_now("Aš negaliu jį ieškoti, dabar esu ne namuose") is True


class TestOtherStreetSignal:
    """A-banga P2 (gyva #4: „mano ADARAS yra Tilžės gatvė 60"): kitos registro
    gatvės vardas + skaitmuo po identifikacijos = korekcijos kandidatas."""

    def _identified(self):
        agent = _agent()
        agent.state.customer_id = "CUST112"
        agent.state.problem_type = "internet_down"
        agent.state.set_customer_info(
            "CUST112", "Paulius Vasiliauskas", "Šiauliai, Vilniaus g. 33-2"
        )
        return agent

    def _turn(self, agent, text):
        # Gyva seka (react_agent ~1416): prefill, tada pre_turn_guards —
        # reopen trigeris gyvena guards'uose, ne prefill'e.
        agent._prefill_slots_from_text(text)
        agent._pre_turn_guards(text)

    def test_garbled_correction_triggers_confirm(self, db_connection):
        agent = self._identified()
        msg = "Atsiprašau su maišiu, mano adaras yra Tilžės gatvė 60"
        self._turn(agent, msg)
        assert agent._reopen_confirm_pending  # kandidatas užfiksuotas
        r = agent._identification_scripted_reply(msg)
        assert r and "KITO adreso" in r  # patvirtinimo klausimas

    def test_own_street_number_is_content(self, db_connection):
        agent = self._identified()
        self._turn(agent, "Nei 1 lemputė nedega ant to routerio")
        assert not getattr(agent, "_reopen_confirm_pending", None)

    def test_no_digit_no_trigger(self, db_connection):
        agent = self._identified()
        self._turn(agent, "Kaimynas iš Tilžės gatvės sakė tas pats")
        assert not getattr(agent, "_reopen_confirm_pending", None)


class TestCodeHoles:
    """A-banga P3 (gyva #3): perspėjimas įjungia klausymą; įrankis normalizuoja
    STT kodą; „kodą mini be skaičių" gauna scripted pagalbą."""

    def test_warning_arms_listening_then_bare_digits_work(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._identification_scripted_reply("Nežinau adreso")
        r = agent._identification_scripted_reply("Negaliu pasakyti")  # warn
        assert r and "negalėsiu" in r
        assert agent._awaiting_account_code is True
        agent._identification_scripted_reply("10104")
        assert agent.state.phone_candidate
        assert agent.state.phone_candidate["customer_id"] == "CUST104"

    def test_tool_normalizes_stt_garbled_code(self, db_connection):
        import json as _json

        from agent.tools import execute_tool

        r = _json.loads(execute_tool("find_customer", {"account_code": "D10104"}))
        assert r["success"] and r["customer_id"] == "CUST104"
        r = _json.loads(execute_tool("find_customer", {"account_code": "ab 10101"}))
        assert r["success"] and r["customer_id"] == "CUST101"

    def test_code_talk_without_digits_gets_scripted_help(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        r = agent._identification_scripted_reply("Nu, gerai, abonento kodą pasakysiu. A. B.")
        assert r and "penki skaitmenys" in r  # scripted, ne LLM haliucinacija

    def test_found_code_is_echoed_with_address(self, db_connection):
        """A-3 skaidrumas: agentas pasako, KOKĮ kodą išgirdo, ir kartu siūlo
        adresą patvirtinimui — klientas pagauna klaidą prieš einant toliau."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        from agent.identification_flow import _account_code_rung

        handled, r = _account_code_rung(agent, agent.state, "Kodas dešimt šimtas keturi, 10104")
        assert handled and r
        assert "Išgirdau kodą" in r and "1 0 1 0 4" in r
        assert "skambinate dėl" in r  # verbatim šerdis — patvirtinimo sargui

    def test_missed_code_is_echoed_too(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        from agent.identification_flow import _account_code_rung

        handled, r = _account_code_rung(agent, agent.state, "AB 99999")
        assert handled and r
        assert "Išgirdau kodą" in r and "9 9 9 9 9" in r and "nerandu" in r
