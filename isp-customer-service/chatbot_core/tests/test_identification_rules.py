"""
Identifikacijos etalono taisyklės (Andrius 2026-09-03, docs/IDENT_TESTAI.md):
№1 butas pagal DB (resolveris jau moka — regresijos sargas), №2/№5 abonento
kodo pakopa + „pagalba tik abonentams", №3 adreso keitimas tik su
patvirtinimu, №4 savininko vardo patikra be DB vardo garsinimo.
"""


def _agent(phone="unknown"):
    from tests.calls import make_agent

    return make_agent(phone)


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
        from agent.decide.rules.identification import _extract_account_code

        assert _extract_account_code("Mano kodas AB-10104") == "AB-10104"
        assert _extract_account_code("ab 10104") == "AB-10104"
        assert _extract_account_code("10104") == "AB-10104"
        assert _extract_account_code("Vilniaus g. 29") is None  # adresas ne kodas
        assert _extract_account_code("nežinau") is None

    def test_code_heard_anytime_without_mode(self, db_connection):
        """Kodas girdimas VISADA — klientas gali jį pasakyti nelaukiamas."""
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        scripted_words(
            agent.state, agent.runtime, "Adreso nežinau, bet turiu abonento kodą AB-10104"
        )
        assert agent.state.identity.phone_candidate
        assert agent.state.identity.phone_candidate["customer_id"] == "CUST104"
        assert agent.state.identity.customer_id is None  # adresas SIŪLOMAS, ne prisiimamas

    def test_empty_turns_warn_then_close_no_location(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True  # adreso klausimas jau nuskambėjo
        r1 = scripted_words(agent.state, agent.runtime, "Nežinau adreso")
        assert not agent.state.closing.case_closed
        r2 = scripted_words(agent.state, agent.runtime, "Negaliu pasakyti")
        assert r2 and "negalėsiu" in r2  # PERSPĖJIMAS (su kodo užuomina)
        scripted_words(agent.state, agent.runtime, "Na nežinau")
        r4 = scripted_words(agent.state, agent.runtime, "Nieko nesakysiu")
        assert agent.state.closing.case_closed and r4 and "nenustačius" in r4
        assert agent.state.ticket.ticket_id is None

    def test_unrecognized_address_offers_code(self, db_connection):
        """Turinys yra, bet registras jo visai neatpažįsta — po 2 siūlom kodą
        (rev.2 2026-09-10: automatinių raidžių nebėra, fuzzy — pagrindinis)."""
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        scripted_words(agent.state, agent.runtime, "Kosmonautų alėja 7")
        r = scripted_words(agent.state, agent.runtime, "Sakau — Kosmonautų alėja septyni")
        assert r and "abonento kodą" in r
        assert agent.state.identity.account_code_mode is True

    def test_code_mode_passes_content_through(self, db_connection):
        """KURTUMO fix: adresas/pavardė kodo režime praleidžiami į normalią
        eigą, o ne atsimuša į „kodas atrodo taip"."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        from agent.decide.rules.identification import _account_code_rung

        handled, reply = _account_code_rung(
            agent.state, agent.runtime, agent.state, "Petraitis, pasižiūrėkit pavardę"
        )
        assert handled is False and reply is None  # praleista — agentas klauso
        handled, reply = _account_code_rung(
            agent.state, agent.runtime, agent.state, "Ginkūnai, Žeimių gatvė 12"
        )
        assert handled is False
        assert agent.state.identity.account_code_mode is False  # režimas tyliai užgeso

    def test_explicit_no_code_closes(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        r = scripted_words(agent.state, agent.runtime, "Neturiu jokio kodo")
        assert agent.state.closing.case_closed and r and "abonentams" in r

    def test_city_not_served_is_instant(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        r = scripted_words(agent.state, agent.runtime, "Vilnius, Gedimino prospektas 1")
        assert r and "Šiaulių mieste ir rajone" in r
        assert not agent.state.closing.case_closed
        assert agent.state.identity.address_empty_turns == 0  # ne bandymas

    def test_clarifying_turns_never_count(self, db_connection):
        """Gyva T-6: pavardės tikslinimas skaitiklių neliečia."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.messages.append(
            {"role": "assistant", "content": "Kokia pavardė, kad galėčiau patvirtinti sutartį?"}
        )
        from agent.decide.rules.identification import _account_code_rung

        for txt in ("Tetraitos", "Petraitis", "Pet raitis sakau"):
            handled, reply = _account_code_rung(agent.state, agent.runtime, agent.state, txt)
            assert handled is False and reply is None
        assert agent.state.identity.address_empty_turns == 0


class TestCitySuggestionWiring:
    """Gyva T-5: „Žeimių g. yra Ginkūnuose" + kliento „taip" → miesto slotas
    persijungia, paieška vyksta ten (tikslinimas nėra bandymai)."""

    def test_confirmation_moves_the_city_slot(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.suggested_city = "Ginkūnai"
        prefill_slots_from_text(agent.state, agent.runtime, "Taip, Ginkūnuose")
        assert agent.state.identity.profile.city.value == "Ginkūnai"
        assert agent.state.identity.suggested_city is None

    def test_bare_yes_also_moves(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.suggested_city = "Ginkūnai"
        prefill_slots_from_text(agent.state, agent.runtime, "Taip taip")
        assert agent.state.identity.profile.city.value == "Ginkūnai"

    def test_other_answer_keeps_suggestion_open(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.identity.suggested_city = "Ginkūnai"
        prefill_slots_from_text(agent.state, agent.runtime, "Palaukite, pasižiūrėsiu dokumentuose")
        assert agent.state.identity.profile.city.value is None
        assert agent.state.identity.suggested_city == "Ginkūnai"


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
        """Naujas adresas be butų (Vilniaus g. 29) — po „taip" identifikacija
        įvyksta TĄ PATĮ turn'ą, be papildomų klausimų."""
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "skambinu dėl Vilniaus gatvės 29"
        agent.state.identity.reopen_confirm_asked = True
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


class TestQuestionRegistry:
    """B banga, žingsnis 1 (shadow): registras atspindi saugiklių klausimus —
    kas klausė, kelintą kartą; skaitytuvai jį valo."""

    def _identified(self):
        agent = _agent(phone="+37060020112")
        agent.state.identity.customer_id = "CUST112"
        agent.state.identity.customer_address = "Šiauliai, Vilniaus g. 33-2"
        agent.state.intake.problem_type = "internet_down"
        return agent

    def test_reopen_lifecycle_ask_reask_close(self, db_connection):
        from agent.decide.question import active
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "dėl Tilžės g. 60"
        agent.state.identity.reopen_confirm_asked = False
        scripted_words(agent.state, agent.runtime, "dėl Tilžės g. 60")  # ask
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "safety" and q.key == "reopen_confirm" and q.asks == 1
        turn_head(agent.state, agent.runtime, "Nu kaip čia pasakyt")  # unclear → reask
        scripted_words(agent.state, agent.runtime, "Nu kaip čia pasakyt")
        q = active(agent.state, agent.runtime)
        assert q and q.asks == 2  # pakartojimas registruotas
        turn_head(agent.state, agent.runtime, "Mhm chm")  # antras neaiškus → nurašyta
        assert active(agent.state, agent.runtime) is None

    def test_reopen_confirmed_clears(self, db_connection):
        from agent.decide.question import active
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.identity.reopen_confirm_utterance = "dėl Vilniaus gatvės 29"
        agent.state.identity.reopen_confirm_asked = False
        scripted_words(agent.state, agent.runtime, "dėl Vilniaus gatvės 29")
        turn_head(agent.state, agent.runtime, "Taip")
        assert active(agent.state, agent.runtime) is None
        assert agent.state.identity.customer_id == "CUST009"

    def test_ticket_question_lifecycle(self, db_connection):
        """B žingsnis 3: tiketo klausimai (numeris → valandos) registre;
        registracija uždaro savininką."""
        from agent.decide.question import active
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.ticket import ticket_stage_reply
        from agent.execute.ticket import begin_ticket_dialogue, finish_ticket_dialogue
        from agent.resolution import get_strategy

        agent = self._identified()
        agent.state.resolution.procedure = {"verdict": "unclear_fault", "step": "escalate"}
        begin_ticket_dialogue(
            agent.state, agent.runtime, get_strategy("unclear_fault").by_role("escalate")
        )
        ticket_stage_reply(agent.state, agent.runtime)
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "ticket" and q.key == "ticket_phone"
        turn_head(agent.state, agent.runtime, "Taip, tiks")
        ticket_stage_reply(agent.state, agent.runtime)
        q = active(agent.state, agent.runtime)
        assert q and q.key == "ticket_hours"
        turn_head(agent.state, agent.runtime, "Po 17 valandos")
        finish_ticket_dialogue(agent.state, agent.runtime)
        assert agent.state.ticket.ticket_id
        assert active(agent.state, agent.runtime) is None  # dialogas baigtas — registras švarus

    def test_walker_evidence_question_closes_on_fact(self, db_connection):
        """B žingsnis 4: įrodymo klausimas registre užsidaro, kai ateina jo
        rakto faktas (kito rakto faktas jo neliečia)."""
        from agent.decide.question import active, register
        from agent.perceive.evidence import ingest_client_evidence

        agent = self._identified()
        register(agent.state, agent.runtime, "walker", "evidence:lights")
        ingest_client_evidence(agent.state, agent.runtime, "Nei viena lemputė nedega")
        assert active(agent.state, agent.runtime) is None
        # kito rakto faktas svetimo klausimo neuždaro
        register(agent.state, agent.runtime, "walker", "evidence:fail_scope")
        ingest_client_evidence(agent.state, agent.runtime, "Kabelis įkištas gerai")
        assert active(agent.state, agent.runtime) is not None

    def test_step_presentation_registers(self, db_connection):
        from agent.decide.question import active
        from agent.execute.step import mark_step_presented

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "unclear_fault",
            "step": "escalate",
            "asked": False,
        }
        mark_step_presented(agent.state, agent.runtime)
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "walker" and q.key == "step:escalate"
        # Gyva 2026-09-08: end-confirm/wrap-up replikos NE žingsnio klausimas —
        # jos nebekelia asks; uždarytas atvejis valo walker savininką.
        agent.state.dialog.end_confirm_pending = True
        mark_step_presented(agent.state, agent.runtime)
        assert active(agent.state, agent.runtime).asks == 1  # nepakito
        agent.state.dialog.end_confirm_pending = False
        agent.state.closing.case_closed = True
        mark_step_presented(agent.state, agent.runtime)
        assert active(agent.state, agent.runtime) is None  # wrap-up fazė — walker uždarytas

    def test_cannot_now_shield_beats_walker_refuse(self, db_connection):
        """P-D gyva: „nepatogu, nesu namuose" — anksčiau walker'io refuse
        guard'as tą patį turn'ą startavo tiketą; dabar galvos skydas
        registruoja safety klausimą ir walker'is laiko."""
        from agent.decide.procedure import advance
        from agent.decide.question import active
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "unclear_fault",
            "step": "escalate",
            "asked": True,
        }
        msg = "Nepatogu man tai daryt, aš nesu namuose dabar."
        turn_head(agent.state, agent.runtime, msg)
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "safety" and q.key == "cannot_now"
        advance(agent.state, agent.runtime, msg)
        assert agent.state.ticket.stage is None  # tiketas NEprasidėjo
        r = scripted_words(agent.state, agent.runtime, msg)
        assert r and "nepatogu" in r  # laiptelis klausia KAS nepatogu

    def test_ability_yes_routes_to_reboot(self, db_connection):
        """P-C: gebėjimo klausimas — „taip" veda į perkrovimo instrukciją."""
        from agent.decide.procedure import advance

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        advance(agent.state, agent.runtime, "Taip, galiu, esu prie routerio")
        assert agent.state.resolution.procedure["step"] == "rh_reboot"

    def test_ability_no_routes_to_homework_then_callback(self, db_connection):
        """P-C: „ne" → namų darbas; sutikimas → callback uždarymas su scripted
        atsisveikinimu, be tiketo."""
        from agent.decide.procedure import advance
        from agent.decide.rules.reply import scripted_words

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        advance(agent.state, agent.runtime, "Ne.")
        assert agent.state.resolution.procedure["step"] == "rh_homework"
        agent.state.resolution.procedure["asked"] = True
        advance(agent.state, agent.runtime, "Taip, sutinku.")
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert agent.state.ticket.ticket_id is None
        r = scripted_words(agent.state, agent.runtime, "Taip, sutinku.")
        assert r and "paskambinkite" in r  # callback_goodbye

    def test_soft_refuse_at_ability_stays_with_pack(self, db_connection):
        """P-C: švelnus „nesu namuose" ability žingsnyje NEeskaluoja į tiketą —
        pack'as pats nuves į homework; aiškus reikalavimas vis tiek laimi."""
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "rh_ability",
            "asked": True,
            "solution_synced": True,
        }
        from agent.decide.question import register

        register(agent.state, agent.runtime, "walker", "step:rh_ability")
        turn_head(agent.state, agent.runtime, "Nepatogu, nesu namuose dabar")
        # skydas NEkyla (pack'o žingsnis valdo), tiketas NEprasidėjo
        from agent.decide.question import active

        q = active(agent.state, agent.runtime)
        assert q and q.key == "step:rh_ability"
        assert agent.state.ticket.stage is None

    def test_homework_no_escalates_with_honest_reason(self, db_connection):
        from agent.decide.procedure import advance
        from agent.decide.rules.ticket import ticket_need

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "rh_homework",
            "asked": True,
            "solution_synced": True,
        }
        advance(agent.state, agent.runtime, "Ne, geriau meistrą registruokim")
        assert agent.state.resolution.procedure.get("escalate_reason")
        need = ticket_need(agent.state, agent.runtime)
        assert "nepavyko" in need and "perkrautas" not in need

    def test_ticket_need_honest_on_refusal(self, db_connection):
        """P-E gyva: „routeris perkrautas, bet ryšys neatsistatė" — melas, kai
        veiksmo nebuvo; atsisakymo/negalėjimo eskalacija sako sąžiningai."""
        from agent.decide.rules.ticket import ticket_need

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "router_hung",
            "step": "escalate",
            "escalate_reason": "cannot_now",
        }
        need = ticket_need(agent.state, agent.runtime)
        assert "nepavyko" in need
        assert "perkrautas" not in need and "neatsistatė" not in need

    def test_priority_guard_holds_walker_on_safety_question(self, db_connection):
        """PERJUNGIMAS (P6): kol atviras safety/ident/ticket klausimas, walker'is
        turn'o neskaito kaip savo žingsnio atsakymo."""
        from agent.decide.procedure import advance
        from agent.decide.question import active, clear_owner, register

        agent = self._identified()
        agent.state.resolution.procedure = {
            "verdict": "unclear_fault",
            "step": "escalate",
            "asked": True,
        }
        register(agent.state, agent.runtime, "safety", "cannot_now_offer")
        advance(agent.state, agent.runtime, "Registruokite meistrą")
        assert agent.state.ticket.stage is None  # walker'is nepradėjo tiketo — laiko
        assert (
            active(agent.state, agent.runtime) is not None
        )  # klausimas gyvas, jį skaito savininkas
        # Klausimui užsidarius — walker'is vėl skaito normaliai.
        clear_owner(agent.state, agent.runtime, "safety")
        advance(agent.state, agent.runtime, "Registruokite meistrą")
        assert agent.state.ticket.stage is not None  # dabar tiketo dialogas prasidėjo

    def test_caller_name_closes_on_capture(self, db_connection):
        """Gyva 2026-09-08: vardo klausimas registre kabėjo atviras po atsakymo."""
        from agent.decide.question import active, register
        from agent.decide.rules.head import turn_head

        agent = self._identified()
        agent.state.identity.result_pending = True
        register(agent.state, agent.runtime, "ident", "caller_name")
        turn_head(agent.state, agent.runtime, "Paulius mano vardas")
        assert agent.state.identity.caller_name == "Paulius"
        assert active(agent.state, agent.runtime) is None

    def test_code_echo_offer_registers_as_address_offer(self, db_connection):
        """Gyva 2026-09-08: kodo echo pasiūla apeidavo _address_move ir likdavo
        neregistruota."""
        from agent.decide.question import active
        from agent.decide.rules.identification import _account_code_rung

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        _account_code_rung(agent.state, agent.runtime, agent.state, "AB 10104")
        q = active(agent.state, agent.runtime)
        assert q and q.owner == "ident" and q.key == "address_offer"

    def test_cannot_now_lifecycle(self, db_connection):
        from agent.decide.question import active
        from agent.decide.rules.reply import scripted_words
        from agent.resolution import get_strategy

        agent = self._identified()
        agent.state.resolution.procedure = {"verdict": "unclear_fault", "step": "escalate"}
        scripted_words(agent.state, agent.runtime, "Ne patogu man dabar")
        q = active(agent.state, agent.runtime)
        assert q and q.key == "cannot_now_clarify"
        scripted_words(agent.state, agent.runtime, "Nesu namie dabar")
        q = active(agent.state, agent.runtime)
        assert q and q.key == "cannot_now_offer"
        r = scripted_words(agent.state, agent.runtime, "Gerai, paskambinsiu vėliau")
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert active(agent.state, agent.runtime) is None


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

    def test_clarify_answer_updates_relation(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.identity.caller_name = "Petras"
        agent.state.identity.caller_relation = "holder"
        agent.state.identity.holder_clarify_open = True
        agent.state.identity.holder_clarify_asked = True  # klausimas jau nuskambėjo
        prefill_slots_from_text(agent.state, agent.runtime, "Žmonos vardu sudaryta sutartis")
        assert agent.state.identity.caller_relation != "holder"


class TestCannotNowLadder:
    """A-banga P1 (gyva #6 2026-09-04: „Ne patogu" ignoruotas): STOP →
    „kas nepatogu?" → registracija / perskambinimas / tęsiam."""

    def _solving(self):
        agent = _agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.intake.problem_type = "internet_down"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_lights"}
        return agent

    def test_cannot_now_asks_what_is_wrong(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._solving()
        r = scripted_words(agent.state, agent.runtime, "Ne patogu")
        assert r and "kas nepatogu" in r
        assert agent.state.dialog.cannot_now_state == "asked"

    def test_confirmed_cannot_offers_paths(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "asked"
        r = scripted_words(agent.state, agent.runtime, "Na, aš ne namie dabar")
        assert r and "užregistruoti" in r and "paskambinkite" in r

    def test_callback_choice_closes_politely(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "offered"
        r = scripted_words(agent.state, agent.runtime, "Geriau pats perskambinsiu vėliau")
        assert agent.state.closing.case_closed and agent.state.closing.closed_reason == "callback"
        assert r and "paskambinkite" in r
        assert agent.state.ticket.ticket_id is None

    def test_ticket_choice_starts_dialogue(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "offered"
        scripted_words(agent.state, agent.runtime, "Registruokite meistrą")
        assert agent.state.ticket.stage == "phone"

    def test_explained_otherwise_resumes(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = self._solving()
        agent.state.dialog.cannot_now_state = "asked"
        r = scripted_words(agent.state, agent.runtime, "Ne ne, viskas gerai, jau radau routerį")
        assert r is None  # kelias tęsiasi
        assert agent.state.dialog.cannot_now_state is None

    def test_in_flow_negaliu_is_not_a_signal(self, db_connection):
        from agent.perceive.detectors import detect_cannot_now

        assert detect_cannot_now("Negaliu prisijungti prie interneto") is False
        assert detect_cannot_now("Negaliu rasti tos dėžutės") is False
        assert detect_cannot_now("Aš negaliu jį ieškoti, dabar esu ne namuose") is True


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
        from agent.perceive.slots import prefill_slots_from_text

        # Gyva seka: prefill, tada pre_turn_guards —
        # reopen trigeris gyvena guards'uose, ne prefill'e.
        prefill_slots_from_text(agent.state, agent.runtime, text)
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


class TestCodeHoles:
    """A-banga P3 (gyva #3): perspėjimas įjungia klausymą; įrankis normalizuoja
    STT kodą; „kodą mini be skaičių" gauna scripted pagalbą."""

    def test_warning_arms_listening_then_bare_digits_work(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        scripted_words(agent.state, agent.runtime, "Nežinau adreso")
        r = scripted_words(agent.state, agent.runtime, "Negaliu pasakyti")  # warn
        assert r and "negalėsiu" in r
        assert agent.state.identity.account_code_mode is True
        scripted_words(agent.state, agent.runtime, "10104")
        assert agent.state.identity.phone_candidate
        assert agent.state.identity.phone_candidate["customer_id"] == "CUST104"

    def test_tool_normalizes_stt_garbled_code(self, db_connection):
        import json as _json

        from agent.tools import execute_tool

        r = _json.loads(execute_tool("find_customer", {"account_code": "D10104"}))
        assert r["success"] and r["customer_id"] == "CUST104"
        r = _json.loads(execute_tool("find_customer", {"account_code": "ab 10101"}))
        assert r["success"] and r["customer_id"] == "CUST101"

    def test_code_talk_without_digits_gets_scripted_help(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        r = scripted_words(agent.state, agent.runtime, "Nu, gerai, abonento kodą pasakysiu. A. B.")
        assert r and "penki skaitmenys" in r  # scripted, ne LLM haliucinacija

    def test_found_code_is_echoed_with_address(self, db_connection):
        """A-3 skaidrumas: agentas pasako, KOKĮ kodą išgirdo, ir kartu siūlo
        adresą patvirtinimui — klientas pagauna klaidą prieš einant toliau."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        from agent.decide.rules.identification import _account_code_rung

        handled, r = _account_code_rung(
            agent.state, agent.runtime, agent.state, "Kodas dešimt šimtas keturi, 10104"
        )
        assert handled and r
        assert "Išgirdau kodą" in r and "1 0 1 0 4" in r
        assert "skambinate dėl" in r  # verbatim šerdis — patvirtinimo sargui

    def test_missed_code_is_echoed_too(self, db_connection):
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        from agent.decide.rules.identification import _account_code_rung

        handled, r = _account_code_rung(agent.state, agent.runtime, agent.state, "AB 99999")
        assert handled and r
        assert "Išgirdau kodą" in r and "9 9 9 9 9" in r and "nerandu" in r
