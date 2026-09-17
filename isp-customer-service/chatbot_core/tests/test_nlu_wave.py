"""
NLU banga (2026-09-09, gyvi P2/kodo-režimo/paraidžiui defektai): žodžių
inkarai skiria namą nuo buto, pilna diktacija prabudina kodo režimą, šio
turn'o diktacija permuša senus slotus, paraidžiui pakopa siaurina registrą.
"""


def _agent(phone="unknown"):
    from tests.calls import make_agent

    return make_agent(phone)


def _read(text):
    from agent.perceive.nlu import extract_address
    from agent.tooling import LocalToolProvider

    registry = LocalToolProvider().address_registry()
    return extract_address(text, registry.streets, registry.localities)


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
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        prefill_slots_from_text(
            agent.state, agent.runtime, "Negaliu pasakyti kodo. Šiauliai, Tilžės gatvė 60, butas 3"
        )
        p = agent.state.identity.profile
        assert p.street.value and "Tilž" in p.street.value
        assert p.house.value == "60" and p.apartment.value == "3"

    def test_bare_digits_stay_silenced(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.account_code_mode = True
        prefill_slots_from_text(agent.state, agent.runtime, "10104")
        assert agent.state.identity.profile.street.value is None


class TestFreshDictationWins:
    """Blokas 3: ŠIO turn'o pilna diktacija permuša senus fragmentus."""

    def test_full_dictation_overrides_stale_house(self, db_connection):
        from agent.perceive.slots import prefill_slots_from_text
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.profile.street.propose("Tilžės g.", 0.92, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("6", 0.92, SlotStatus.HEARD)
        agent.state.identity.profile.apartment.propose("60", 0.92, SlotStatus.HEARD)
        prefill_slots_from_text(
            agent.state, agent.runtime, "Sakau — Šiauliai, Tilžės gatvė 60, butas 3"
        )
        p = agent.state.identity.profile
        assert p.house.value == "60" and p.apartment.value == "3"


class TestSpellingRung:
    """Blokas 4 (Andriaus idėja): paraidžiui su inkaro žodžiais."""

    def test_spell_prefix_parsing(self):
        from agent.decide.rules.identification import _spell_prefix

        assert _spell_prefix("V kaip Vilnius, I kaip Ieva, L kaip Lina") == "vil"
        assert _spell_prefix("Kaunas Upė Kelias") == "kuk"  # be „kaip" — pirmos raidės
        assert _spell_prefix("") == ""

    def test_prefix_narrows_registry(self, db_connection):
        from agent.decide.rules.identification import _street_by_prefix

        agent = _agent()
        cand = _street_by_prefix(agent.state, agent.runtime, "vil")
        assert cand and cand.lower().startswith("vil")  # dabar VIL turi 2 kandidatus

    def test_two_unrecognized_offers_code(self, db_connection):
        """rev.2: automatinių raidžių NEBĖRA — po 2 neatpažintų kodas."""
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        scripted_words(agent.state, agent.runtime, "Kosmonautų alėja 7")
        r = scripted_words(agent.state, agent.runtime, "Sakau — Kosmonautų alėja septyni")
        assert r and "abonento kodą" in r

    def test_spell_answer_matches_street_and_asks_house(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        agent.state.identity.spell_mode = True
        r = scripted_words(agent.state, agent.runtime, "V kaip Vilnius, I kaip Ieva, L kaip Lina")
        assert r and ("Vil" in r) and "namo" in r  # VIL pogrupio kandidatas
        assert (
            agent.state.identity.profile.street.value
            and agent.state.identity.profile.street.value.lower().startswith("vil")
        )

    def test_resolve_loop_offers_code(self, db_connection):
        """rev.2: resolve loopas (3 nesėkmės) → kodas, be raidžių."""
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        agent.state.identity.address_resolve_failures = 3
        r = scripted_words(agent.state, agent.runtime, "Tilžiatkas gatvė 6")
        assert r and "abonento kodą" in r

    def test_denied_street_dropped_and_not_reread(self, db_connection):
        """D1 (gyva 2026-09-10): „apie Žeimių gatvę nieko NESAKIAU" — slotas
        išmetamas ir iš paties neigimo sakinio gatvė NEgrįžta."""
        from agent.perceive.slots import prefill_slots_from_text
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
        agent.state.identity.profile.house.propose("60", 1.0, SlotStatus.HEARD)
        prefill_slots_from_text(agent.state, agent.runtime, "Aš apie Žeimių gatvę nieko nesakiau")
        assert agent.state.identity.profile.street.value is None
        assert agent.state.identity.address_resolve_failures >= 1  # žingsnis link paraidžiui

    def test_denial_with_correction_keeps_new_street(self, db_connection):
        """D1: „nesakiau Žeimių — Tilžės gatvė 60" — pataisymas išgyvena."""
        from agent.perceive.slots import prefill_slots_from_text
        from agent.slots import SlotStatus

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.profile.street.propose("Žeimių g.", 1.0, SlotStatus.HEARD)
        prefill_slots_from_text(agent.state, agent.runtime, "Nesakiau Žeimių — Tilžės gatvė 60")
        assert (
            agent.state.identity.profile.street.value
            and "Tilž" in agent.state.identity.profile.street.value
        )
        assert agent.state.identity.profile.house.value == "60"

    def test_spell_prefix_client_form(self):
        """Kliento spontaniška forma: inkaras PO „kaip" (gyva: „Taip kaip
        tėtis ir kaip Ignas" = T, I)."""
        from agent.decide.rules.identification import _spell_prefix

        assert _spell_prefix("Taip kaip tėtis ir kaip Ignas") == "ti"
        assert _spell_prefix("K kaip Kaunas, U kaip upė") == "ku"

    def test_attempt_tracker_verdicts(self, db_connection):
        """rev.2: identiškas pakartojimas = išgirsta TEISINGAI (gatvės nėra);
        panašus-bet-kitoks = ASR nestabilus; skirtingi žodžiai — nieko."""
        from agent.decide.rules.identification import _register_street_attempt

        agent = _agent()
        assert _register_street_attempt(agent.state, agent.runtime, "Kosmonautų") is None
        assert (
            _register_street_attempt(agent.state, agent.runtime, "Kosmonautų gatvė") == "identical"
        )
        agent2 = _agent()
        assert _register_street_attempt(agent2.state, agent2.runtime, "Šilkės") is None
        assert _register_street_attempt(agent2.state, agent2.runtime, "Čilkes") == "similar"
        agent3 = _agent()
        assert _register_street_attempt(agent3.state, agent3.runtime, "Šilkės") is None
        assert _register_street_attempt(agent3.state, agent3.runtime, "Kosmonautų") is None

    def test_identical_repeat_says_street_not_exists(self, db_connection):
        """rev.2 (gyva Kosmonautų): tas pats žodis pakartotas — sąžininga
        riba („tokios gatvės nerandu... ar tikrai mūsų klientas?"), ne
        raidės/kodo spaudimas ir ne uždarymas."""
        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        agent.state.messages.append(
            {"role": "assistant", "content": "Gal galėtumėte pakartoti gatvės pavadinimą?"}
        )
        from agent.decide.rules.identification import _account_code_rung, _register_street_attempt

        _register_street_attempt(agent.state, agent.runtime, "Kosmonautų")  # pirmas girdėjimas
        handled, r = _account_code_rung(agent.state, agent.runtime, agent.state, "Kosmonautų.")
        assert handled and r and "nerandu" in r and "mieste" in r  # pirma MIESTAS
        assert agent.state.identity.account_code_mode is True  # kodas girdimas, jei pasakys
        assert not agent.state.closing.case_closed

    def test_letters_filter_garble_in_subset(self, db_connection):
        """Raidė + darkinys kartu: prefiksas „t" + girdėtas „Tilžiuko" →
        Tilžės g. (fuzzy pogrupyje)."""
        from agent.decide.rules.identification import _street_by_prefix_and_garble

        agent = _agent()
        cand = _street_by_prefix_and_garble(agent.state, agent.runtime, "t", "tilziuko")
        assert cand and cand.lower().startswith("til")  # TIL pogrupis: Tilžės/Tilvyčio

    def test_client_initiated_kaip_pairs_read_as_letters(self, db_connection):
        """R3: klientas pats raidžiuoja be režimo — „kaip X" poros girdimos."""
        from agent.decide.rules.identification import _register_street_attempt
        from agent.decide.rules.reply import scripted_words

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.anamnesis_asked = True
        _register_street_attempt(agent.state, agent.runtime, "Tilžiuko")
        r = scripted_words(
            agent.state, agent.runtime, "Taip kaip Tomas ir kaip Ieva, taip kaip Lina"
        )
        assert r and ("Tilž" in r or "namo" in r)  # raidės TIL → Tilžės

    def test_first_sighting_triggers_nothing(self, db_connection):
        """Andrius: pirmas girdėjimas — jokių specialių šakų."""
        from agent.decide.rules.identification import _register_street_attempt

        agent = _agent()
        assert _register_street_attempt(agent.state, agent.runtime, "Kosmonautų") is None
        assert agent.state.identity.street_not_exists_due is False

    def test_spell_turn_prefill_silent(self, db_connection):
        """„K kaip Kaunas" spell turn'e NEtampa miestu Kaunu."""
        from agent.perceive.slots import prefill_slots_from_text

        agent = _agent()
        agent.state.intake.problem_type = "internet_down"
        agent.state.identity.spell_mode = True
        prefill_slots_from_text(agent.state, agent.runtime, "K kaip Kaunas, U kaip upė")
        assert agent.state.identity.profile.city.value is None
