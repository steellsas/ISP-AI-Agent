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
        assert cand and "Vilniaus" in cand

    def test_two_unrecognized_then_spell_then_code(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._identification_scripted_reply("Kosmonautų alėja 7")
        r = agent._identification_scripted_reply("Sakau — Kosmonautų alėja septyni")
        assert r and "paraidžiui" in r  # pirma paraidžiui, ne kodas
        assert agent._spell_mode is True
        # nepavykusi paraidžiui (neatpažįstamos raidės) → kodo pakopa
        r2 = agent._identification_scripted_reply("Nu nežinau ką čia sakot")
        assert r2 and "abonento kodą" in r2

    def test_spell_answer_matches_street_and_asks_house(self, db_connection):
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._spell_mode = True
        agent._spell_done = True
        r = agent._identification_scripted_reply("V kaip Vilnius, I kaip Ieva, L kaip Lina")
        assert r and "Vilniaus" in r and "namo" in r
        assert agent.state.profile.street.value and "Vilniaus" in agent.state.profile.street.value

    def test_resolve_loop_offers_spelling_first(self, db_connection):
        """Gyva 2026-09-10: darkytos gatvės loopas ėjo per RESOLVE nesėkmes ir
        šoko tiesiai į kodą — paraidžiui pirmiau ir šiame kanale."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._addr_resolve_fails = 3
        r = agent._identification_scripted_reply("Tilžiatkas gatvė 6")
        assert r and "paraidžiui" in r
        # antrą kartą (spell jau išnaudotas) — kodas
        agent._addr_resolve_fails = 3
        agent._spell_mode = False
        r2 = agent._identification_scripted_reply("Vis tiek nesigauna")
        assert r2 and "abonento kodą" in r2

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

    def test_rejected_suggestions_go_to_spelling(self, db_connection):
        """D2: resolverio pasiūlymai atmesti be naujos gatvės → paraidžiui."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        agent._addr_suggested = True
        r = agent._identification_scripted_reply("Ne, nei viena netinka")
        assert r and "paraidžiui" in r
        assert agent._spell_mode is True

    def test_spell_turn_prefill_silent(self, db_connection):
        """„K kaip Kaunas" spell turn'e NEtampa miestu Kaunu."""
        agent = _agent()
        agent.state.problem_type = "internet_down"
        agent._spell_mode = True
        agent._prefill_slots_from_text("K kaip Kaunas, U kaip upė")
        assert agent.state.profile.city.value is None
