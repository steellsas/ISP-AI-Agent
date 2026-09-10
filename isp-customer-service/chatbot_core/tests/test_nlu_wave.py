"""
NLU banga (2026-09-09, gyvi P2/kodo-režimo/paraidžiui defektai): žodžių
inkarai skiria namą nuo buto, pilna diktacija prabudina kodo režimą, šio
turn'o diktacija permuša senus slotus, paraidžiui pakopa siaurina registrą.
"""


def _agent(phone="unknown"):
    from agent.react_agent import ReactAgent

    return ReactAgent(caller_phone=phone)


def _read(text):
    from agent.nlu import extract_address, load_registry
    from agent.tools import get_db

    streets, localities = load_registry(get_db())
    return extract_address(text, streets, localities)


class TestWordAnchors:
    """Blokas 1: „namo/butas" žodis prie skaičiaus sprendžia slotą."""

    def test_namo_numeris_goes_to_house(self, db_connection):
        r = _read("Ne. Tai but... but namo numeris yra 60")
        assert r.house == "60"
        assert r.apartment is None  # nukirptas „but" (3 raidės) — ne žymeklis

    def test_number_before_namas_is_house(self, db_connection):
        r = _read("Tilžės 60 būtų namas, o butas 3")
        assert r.house == "60" and r.apartment == "3"

    def test_glued_single_digits(self, db_connection):
        """„6 0" (šeši nulis) = 60, ne namas 6."""
        r = _read("Tildžės 6 0 būtų namas, o butas 3")
        assert r.house == "60" and r.apartment == "3"

    def test_regular_reading_unchanged(self, db_connection):
        r = _read("Šiauliai, Tilžės gatvė 60, butas 3")
        assert r.street and "Tilž" in r.street
        assert r.house == "60" and r.apartment == "3"

    def test_two_digit_numbers_never_glue(self, db_connection):
        r = _read("Vilniaus gatvė 33 butas 2")
        assert r.house == "33" and r.apartment == "2"


class TestCodeModeDictation:
    """Blokas 2: pilna diktacija kodo režime prabudina adresų skaitytuvą."""

    def test_full_dictation_wakes_reader(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        agent._prefill_slots_from_text("Negaliu pasakyti kodo. Šiauliai, Tilžės gatvė 60, butas 3")
        p = agent.state.profile
        assert p.street.value and "Tilž" in p.street.value
        assert p.house.value == "60" and p.apartment.value == "3"

    def test_bare_digits_stay_silenced(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._awaiting_account_code = True
        agent._prefill_slots_from_text("10104")
        assert agent.state.profile.street.value is None


class TestFreshDictationWins:
    """Blokas 3: ŠIO turn'o pilna diktacija permuša senus fragmentus."""

    def test_full_dictation_overrides_stale_house(self, db_connection):
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.profile.street.propose("Tilžės g.", 0.92, SlotStatus.HEARD)
        agent.state.profile.house.propose("6", 0.92, SlotStatus.HEARD)
        agent.state.profile.apartment.propose("60", 0.92, SlotStatus.HEARD)
        agent._prefill_slots_from_text("Sakau — Šiauliai, Tilžės gatvė 60, butas 3")
        p = agent.state.profile
        assert p.house.value == "60" and p.apartment.value == "3"


class TestSpellingRung:
    """Blokas 4 (Andriaus idėja): paraidžiui su inkaro žodžiais."""

    def test_spell_prefix_parsing(self):
        from agent.identification_flow import _spell_prefix

        assert _spell_prefix("V kaip Vilnius, I kaip Ieva, L kaip Lina") == "vil"
        assert _spell_prefix("Kaunas Upė Kelias") == "kuk"  # be „kaip" — pirmos raidės
        assert _spell_prefix("") == ""

    def test_prefix_narrows_registry(self, db_connection):
        from agent.identification_flow import _street_by_prefix

        agent = _agent()
        cand = _street_by_prefix(agent, "vil")
        assert cand and cand.lower().startswith("vil")  # dabar VIL turi 2 kandidatus

    def test_two_unrecognized_offers_code(self, db_connection):
        """rev.2: automatinių raidžių NEBĖRA — po 2 neatpažintų kodas."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._identification_scripted_reply("Kosmonautų alėja 7")
        r = agent._identification_scripted_reply("Sakau — Kosmonautų alėja septyni")
        assert r and "abonento kodą" in r

    def test_spell_answer_matches_street_and_asks_house(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._spell_mode = True
        agent._spell_done = True
        r = agent._identification_scripted_reply("V kaip Vilnius, I kaip Ieva, L kaip Lina")
        assert r and ("Vil" in r) and "namo" in r  # VIL pogrupio kandidatas
        assert (
            agent.state.profile.street.value
            and agent.state.profile.street.value.lower().startswith("vil")
        )

    def test_resolve_loop_offers_code(self, db_connection):
        """rev.2: resolve loopas (3 nesėkmės) → kodas, be raidžių."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._addr_resolve_fails = 3
        r = agent._identification_scripted_reply("Tilžiatkas gatvė 6")
        assert r and "abonento kodą" in r

    def test_denied_street_dropped_and_not_reread(self, db_connection):
        """D1 (gyva 2026-09-10): „apie Žeimių gatvę nieko NESAKIAU" — slotas
        išmetamas ir iš paties neigimo sakinio gatvė NEgrįžta."""
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
        agent.state.profile.house.propose("60", 1.0, SlotStatus.HEARD)
        agent._prefill_slots_from_text("Aš apie Žeimių gatvę nieko nesakiau")
        assert agent.state.profile.street.value is None
        assert agent._addr_resolve_fails >= 1  # žingsnis link paraidžiui

    def test_denial_with_correction_keeps_new_street(self, db_connection):
        """D1: „nesakiau Žeimių — Tilžės gatvė 60" — pataisymas išgyvena."""
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
        agent._prefill_slots_from_text("Nesakiau Žeimių — Tilžės gatvė 60")
        assert agent.state.profile.street.value and "Tilž" in agent.state.profile.street.value
        assert agent.state.profile.house.value == "60"

    def test_spell_prefix_client_form(self):
        """Kliento spontaniška forma: inkaras PO „kaip" (gyva: „Taip kaip
        tėtis ir kaip Ignas" = T, I)."""
        from agent.identification_flow import _spell_prefix

        assert _spell_prefix("Taip kaip tėtis ir kaip Ignas") == "ti"
        assert _spell_prefix("K kaip Kaunas, U kaip upė") == "ku"

    def test_attempt_tracker_verdicts(self, db_connection):
        """rev.2: identiškas pakartojimas = išgirsta TEISINGAI (gatvės nėra);
        panašus-bet-kitoks = ASR nestabilus; skirtingi žodžiai — nieko."""
        from agent.identification_flow import _register_street_attempt

        agent = _agent()
        assert _register_street_attempt(agent, "Kosmonautų") is None
        assert _register_street_attempt(agent, "Kosmonautų gatvė") == "identical"
        agent2 = _agent()
        assert _register_street_attempt(agent2, "Šilkės") is None
        assert _register_street_attempt(agent2, "Čilkes") == "similar"
        agent3 = _agent()
        assert _register_street_attempt(agent3, "Šilkės") is None
        assert _register_street_attempt(agent3, "Kosmonautų") is None

    def test_identical_repeat_says_street_not_exists(self, db_connection):
        """rev.2 (gyva Kosmonautų): tas pats žodis pakartotas — sąžininga
        riba („tokios gatvės nerandu... ar tikrai mūsų klientas?"), ne
        raidės/kodo spaudimas ir ne uždarymas."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._last_agent_question = lambda: "Gal galėtumėte pakartoti gatvės pavadinimą?"
        from agent.identification_flow import _account_code_rung, _register_street_attempt

        _register_street_attempt(agent, "Kosmonautų")  # pirmas girdėjimas
        handled, r = _account_code_rung(agent, agent.state, "Kosmonautų.")
        assert handled and r and "nerandu" in r and "mieste" in r  # pirma MIESTAS
        assert agent._awaiting_account_code is True  # kodas girdimas, jei pasakys
        assert not agent.state.case_closed

    def test_letters_filter_garble_in_subset(self, db_connection):
        """Raidė + darkinys kartu: prefiksas „t" + girdėtas „Tilžiuko" →
        Tilžės g. (fuzzy pogrupyje)."""
        from agent.identification_flow import _street_by_prefix_and_garble

        agent = _agent()
        cand = _street_by_prefix_and_garble(agent, "t", "tilziuko")
        assert cand and cand.lower().startswith("til")  # TIL pogrupis: Tilžės/Tilvyčio

    def test_client_initiated_kaip_pairs_read_as_letters(self, db_connection):
        """R3: klientas pats raidžiuoja be režimo — „kaip X" poros girdimos."""
        from agent.identification_flow import _register_street_attempt

        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        _register_street_attempt(agent, "Tilžiuko")
        r = agent._identification_scripted_reply("Taip kaip Tomas ir kaip Ieva, taip kaip Lina")
        assert r and ("Tilž" in r or "namo" in r)  # raidės TIL → Tilžės

    def test_first_sighting_triggers_nothing(self, db_connection):
        """Andrius: pirmas girdėjimas — jokių specialių šakų."""
        from agent.identification_flow import _register_street_attempt

        agent = _agent()
        assert _register_street_attempt(agent, "Kosmonautų") is None
        assert agent._street_not_exists_due is False

    def test_spell_turn_prefill_silent(self, db_connection):
        """„K kaip Kaunas" spell turn'e NEtampa miestu Kaunu."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._spell_mode = True
        agent._prefill_slots_from_text("K kaip Kaunas, U kaip upė")
        assert agent.state.profile.city.value is None
