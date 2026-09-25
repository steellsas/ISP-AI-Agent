"""
Fault packs (R5) — one file per fault + reusable modules + meta/tags.

Packs build their procedure through module calls; the knowledge schema tests
(test_knowledge_schema.py) guard the structure.
"""

from agent.call_record.finalizer import build_call_summary, finalize
from agent.faults import (
    _modules,
    build_strategy,
    fault_meta,
    step_options,
)
from agent.graph_v2.state import (
    ClosingState,
    DiagnosisState,
    DialogState,
    GraphState,
    IdentityState,
    IntakeState,
    ResolutionState,
    TicketContext,
    TicketState,
    TurnScratch,
)

from tests.engine_fakes import as_call


class TestModuleExpansion:
    """Packs compose modules; answers resolve through the expanded steps."""

    def test_step_options_resolve_through_modules(self):
        # answers must be found for module-expanded ids too (instance override wins)
        assert step_options("no_mac_observed", "dr_verify") == {
            "yes": "prijungtame kompiuteryje internetas dabar veikia",
            "no": "prijungtame kompiuteryje interneto vis tiek nėra",
        }
        assert step_options("foreign_mac", "confirm_change")


class TestModulesAndMeta:
    def test_modules_load(self):
        mods = _modules()
        assert "verify_restored" in mods
        assert "bind_mac" in mods
        assert mods["verify_restored"]["exits"] == ["success", "failure"]

    def test_meta(self):
        meta = fault_meta("no_mac_observed")
        assert meta.get("domain") == "internet"


class TestVoiceTestFixes:
    """2026-08-13 live-call fixes: polarity, early facts, phase gating, glosses."""

    def test_negated_demand_is_not_a_demand(self):
        from agent.perceive.detectors import detect_refuse_or_ticket

        assert detect_refuse_or_ticket("Neregistruokite, pajunkim kompiuterį") != "demand"
        assert detect_refuse_or_ticket("užregistruokit gedimą") == "demand"

    def test_demand_with_stop_words_keeps_the_dialogue(self):
        from types import SimpleNamespace

        from agent.decide.rules.ticket import wants_to_keep_solving

        # live phrase: negated solving verbs + explicit demand -> NOT keep-solving
        assert (
            wants_to_keep_solving(
                None,
                None,
                "Nebe noriu tikrinti toliau, užregistruokit gedimą ir nebesprendžiam",
            )
            is False
        )
        assert wants_to_keep_solving(None, None, "Ne, pajunkim tą kompiuterį") is True

    def test_aciu_nereikia_is_a_farewell(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Ačiū, nereikia") is True
        assert detect_farewell("Nebereikia.") is True
        assert detect_farewell("Ačiū") is False

    def test_the_call_so_far_seeds_the_ledger_on_activation(self, monkeypatch):
        from types import SimpleNamespace

        from agent.execute.diagnosis import _seed_evidence_from_call

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    intake=IntakeState(anamnesis_raw="Ką kečiau, routere?"),
                    resolution=ResolutionState(
                        procedure={"verdict": "foreign_mac", "step": "confirm_change"}
                    ),
                    diagnosis=DiagnosisState(evidence={}),
                    dialog=DialogState(turn_count=1),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        _seed_evidence_from_call(engine.state, engine.runtime)
        assert engine.state.diagnosis.evidence.get("changed_device", {}).get("value") == "yes"

    def test_the_opening_sentence_seeds_too(self, monkeypatch):
        """F-11: a fact stated in the very first sentence must not be re-asked once the
        pack activates ("neveikia visuose įrenginiuose" -> "visuose ar tik viename?")."""
        from types import SimpleNamespace

        from agent.execute.diagnosis import _seed_evidence_from_call

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    intake=IntakeState(
                        heard_utterances=["Neveikia internetas visuose įrenginiuose"]
                    ),
                    resolution=ResolutionState(
                        procedure={"verdict": "router_hung", "step": "rh_ability"}
                    ),
                    diagnosis=DiagnosisState(evidence={}),
                    dialog=DialogState(turn_count=1),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        _seed_evidence_from_call(engine.state, engine.runtime)
        assert engine.state.diagnosis.evidence.get("fail_scope", {}).get("value") == "all"

    def test_pack_glosses_replace_raw_keys(self):
        from agent.evidence import gloss_label, gloss_value

        assert gloss_label("changed_device") == "routerio keitimas"
        assert gloss_value("yes", "changed_device") == "keitė arba prijungė naują įrenginį"
        assert gloss_label("lights") == "routerio lemputės"  # built-ins keep working


class TestWhatTheCardsDeclare:
    """Wave 3: the analysis knowledge is the CARD's — which facts are in play, what values
    they take, when a question is worth asking and why we are asking it."""

    def test_every_fault_in_play_declares_its_client_facts(self):
        from agent.evidence import spec_for

        for fault in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            spec = spec_for(fault)
            assert spec is not None and spec.get("client"), fault

    def test_the_foreign_device_asks_what_changes_the_fix(self):
        from agent.contract import cards as catalog

        card = catalog.card("foreign_mac")
        assert set(card.needs) == {"changed_device", "cable_port"}
        assert set(card.needs["changed_device"].answers) == {"yes", "no"}

    def test_a_question_waits_for_the_one_before_it(self):
        """The cable type means nothing until we know it is a computer; the reboot question
        only matters when it fails everywhere."""
        from agent.contract import cards as catalog

        card = catalog.card("healthy_to_router")
        assert card.needs["connection_type"].when == ["fail_device=computer"]
        assert card.needs["rebooted"].when == ["fail_scope=all"]
        assert card.needs["fail_device"].when == ["fail_scope=one"]

    def test_every_question_can_be_asked_and_read(self):
        """A need must have the words to ask it and a way to read the answer — otherwise the
        engine asks something it cannot understand."""
        from agent.contract import cards as catalog
        from agent.contract.locale import load_locale

        locale = load_locale("lt")
        for name, card in catalog.cards().items():
            for fact, need in card.needs.items():
                if need.volunteered:
                    # Never asked: used only when the caller says it themselves (wave 4a —
                    # "esu prie routerio, lemputės dega" confirms a hung router on the spot).
                    assert not need.ask and not need.probe, f"{name}.{fact}: asked after all"
                    continue
                assert need.ask or need.probe, f"{name}.{fact}: no way to get it"
                if need.ask:
                    assert locale.has(need.ask), f"{name}.{fact}: the question is missing"
                if need.why:
                    assert locale.has(need.why), f"{name}.{fact}: the reason is missing"


class TestIdentificationF:
    """F (2026-08-20): identifikacija kaip pokalbis — pasakyk, ką radai ir ko
    ne; paragink su KODĖL; nesėkmę užfiksuok įraše."""

    def test_diag_street_found_house_not(self):
        from agent.execute.identification import address_diag_note

        note = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {"status": "ok", "matched": "Vilniaus g."},
                    "house": {"status": "not_found", "given": "39", "known_houses": [29, 31]},
                    "apartment": {"status": "skipped"},
                },
            }
        )
        assert note and "RANDU" in note and "39" in note and "29" in note

    def test_diag_street_elsewhere_and_fuzzy(self):
        from agent.execute.identification import address_diag_note

        note = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {
                        "status": "not_in_city",
                        "given": "Vilniaus g.",
                        "found_elsewhere": [{"city": "Kuršėnai"}],
                    },
                    "house": {"status": "skipped"},
                },
            }
        )
        assert note and "NERANDU" in note and "Kuršėnai" in note
        fuzzy = address_diag_note(
            {
                "success": False,
                "resolution": {
                    "city": {"status": "ok", "matched": "Šiauliai"},
                    "street": {"status": "unclear", "fuzzy_candidates": ["Vytauto", "Vilniaus"]},
                    "house": {"status": "skipped"},
                },
            }
        )
        assert fuzzy and "Vytauto" in fuzzy
        assert address_diag_note({"success": False, "resolution": {}}) is None

    def test_diag_note_lands_in_facts_block(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.address_lookup_note = "- ADRESO PAIEŠKOS DIAGNOZĖ: gatvę RANDU, namo NĖRA."
        block = context_card(agent.state, agent.runtime)
        assert block and "ADRESO PAIEŠKOS DIAGNOZĖ" in block

    def test_encouragement_appears_once(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        agent.state.dialog.turn_count = 5
        first = context_card(agent.state, agent.runtime) or ""
        second = context_card(agent.state, agent.runtime) or ""
        assert "ADDRESS ENCOURAGEMENT" in first
        assert "ADDRESS ENCOURAGEMENT" not in second

    def test_failed_identification_lands_on_the_record(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        agent.state.intake.heard_utterances.extend(["neveikia internetas", "Vilnaus gatve kazkur"])
        summary = build_call_summary(agent.state, agent.runtime)
        fail = summary["identifikacija_nepavyko"]
        assert fail and "Vilnaus gatve kazkur" in fail["girdeta"]

    def test_short_ladder_phrases(self):
        from agent.contract.locale import phrase

        assert (
            phrase("identification.address_ask")
            == "Gerai — patikrinsiu ryšį iki jūsų buto. Koks adresas?"
        )
        assert "patikrinsiu ryšį" in phrase("identification.address_offer", address="X")


class TestTicketDirectives:
    """Zone 1 (skriptai -> direktyvos): the ticket dialogue's question moments
    become narrator goal directives; retries/cancel stay scripted; off reverts."""

    def _agent(self, db_connection=None):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "escalate"}
        agent.state.ticket.stage = "phone"
        agent.state.ticket.context = TicketContext(step_id=None)
        return agent

    def test_phone_intro_goes_to_narrator(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "nepatogu, ne namuose")
        assert reply is None  # the narrator takes the turn
        td = agent.state.turn.directives.ticket
        assert td and td["kind"] == "phone_intro" and "numeris" in td["fallback"]
        block = context_card(agent.state, agent.runtime)
        assert "TICKET STEP" in block and "registering a technician" in block

    def test_off_switch_keeps_scripted(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "gerai")
        assert reply and "Ar tiks numeris" in reply
        assert agent.state.turn.directives.ticket is None

    def test_retry_stays_scripted_even_in_narrator_mode(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        agent.state.ticket.context.ask_retry = "phone"
        reply = scripted_words(agent.state, agent.runtime, "kazkas neaisku")
        assert reply and "skaitmenimis" in reply  # precision repeat, no LLM
        assert agent.state.turn.directives.ticket is None

    def test_hours_directive(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        agent.state.ticket.stage = "hours"
        agent.state.ticket.context = TicketContext(step_id=None, intro_done=True)
        assert scripted_words(agent.state, agent.runtime, "tiks tas") is None
        assert agent.state.turn.directives.ticket["kind"] == "hours"
        assert "patogiausia" in context_card(agent.state, agent.runtime)


class TestIdentDirectives:
    """Zone 2: the transition to the address becomes a narrator goal directive;
    the OFFER question core stays verbatim (confirm guard); off reverts."""

    def _agent(self, candidate=True):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        if candidate:
            agent.state.identity.phone_candidate = {
                "customer_id": "CUST009",
                "name": "Test",
                "address": "Šiauliai, Vilniaus g. 29",
                "street": "Vilniaus g.",
                "house": "29",
                "apartment": None,
                "city": "Šiauliai",
            }
        return agent

    def test_offer_goes_to_narrator_with_verbatim_core(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "Vakar po audros dingo")
        assert reply is None
        idd = agent.state.turn.directives.ident
        assert idd and idd["kind"] == "address_offer" and "Vilniaus g. 29" in idd["adresas"]
        block = context_card(agent.state, agent.runtime)
        assert "Ar skambinate dėl Vilniaus g. 29?" in block  # verbatim core kept

    def test_ask_goes_to_narrator_without_candidate(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent(candidate=False)
        assert scripted_words(agent.state, agent.runtime, "Vakar po audros dingo") is None
        assert agent.state.turn.directives.ident["kind"] == "address_ask"
        assert "IDENTIFICATION STEP" in context_card(agent.state, agent.runtime)

    def test_off_switch_keeps_scripted_offer(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = self._agent()
        reply = scripted_words(agent.state, agent.runtime, "Vakar po audros dingo")
        assert reply and "Ar skambinate dėl Vilniaus g. 29?" in reply
        assert agent.state.turn.directives.ident is None


class TestAnamnesisDirectives:
    """DIALOGO_ETALONAS #2 (2026-09-03): the OPENING anamnesis question is
    GONE — the ladder goes straight to the address; capture-first keeps what
    the opener already said; the targeted anamnesis lives in the packs."""

    def test_no_opening_question_straight_to_address(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        assert scripted_words(agent.state, agent.runtime, "Neveikia internetas") is None
        assert agent.state.intake.anamnesis_asked is True  # ladder-live marker stays
        assert agent.state.turn.directives.ident["kind"] in ("address_offer", "address_ask")
        block = context_card(agent.state, agent.runtime)
        assert "ANAMNEZĖS ŽINGSNIS" not in block
        assert "IDENTIFICATION STEP" in block

    def test_opening_capture_still_lands(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        agent.state.intake.problem_type = "internet_down"
        scripted_words(agent.state, agent.runtime, "Neveikia internetas nuo vakar, po audros")
        assert agent.state.intake.anamnesis_when  # capture-first read the opener
        assert agent.state.intake.opening_heard_note is True

    def test_the_card_carries_the_contextual_anamnesis(self, db_connection):
        """Only the caller knows whether the power went out or a storm passed — and that is
        what explains a device dropping off the line."""
        from agent.contract import cards as catalog
        from agent.contract.locale import phrase

        need = catalog.card("no_mac_observed").needs["recent_events"]
        assert "elektra" in phrase(need.ask)
        assert "linijoje nesimato" in phrase(need.why)  # the telemetry context


class TestDirectiveTurnsAreSpeechOnly:
    """Live 2026-08-20: with tools exposed the model grabbed resolve_address on
    the anamnesis directive turn and skipped the ladder — directive turns get
    NO tools; the engine owns the mechanics."""

    def test_the_speaker_never_gets_tools(self, db_connection):
        """M5: the speaker has no tools at all — the engine ran every lookup and action."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from agent.graph_v2.runtime import narrate

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.ident = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        captured = {}

        def _stream(**kwargs):
            captured.update(kwargs)
            yield "ok"
            return SimpleNamespace(content="ok", tool_calls=None)

        with (
            patch("agent.speak.node.stream_tool_completion", side_effect=_stream),
            patch("agent.speak.node.get_last_call_stats", return_value={}),
        ):
            narrate(agent.state, agent.runtime, "taip", "intake", "address_validation")
        assert captured["tools"] is None


class TestDetourResilience:
    """Live 2026-08-20: a bare 'Ne.' read as farewell derailed the recap ->
    findings chain and the agent re-ran diagnostics it already had."""

    def test_bare_ne_is_never_a_farewell(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Ne.") is False
        assert detect_farewell("Ne") is False
        assert detect_farewell("Ne, ačiū") is True  # real closer kept
        assert detect_farewell("Viso gero") is True

    def test_split_ne_symptom_polarity(self):
        from agent.perceive.nlu import extract_symptoms

        assert extract_symptoms("Ne 1 lemputė ne dega.").get("lights") == "off"
        assert extract_symptoms("lemputės nedega").get("lights") == "off"

    def test_resync_note_renders_once(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_lights"}
        from agent.evidence import CLIENT, set_fact

        set_fact(agent.state.diagnosis.evidence, "lights", "off", CLIENT, 1)
        agent.state.dialog.resync_note = True
        block = context_card(agent.state, agent.runtime)
        assert "BACK TO SOLVING" in block and "established" in block
        assert "GRĮŽTAME" not in (context_card(agent.state, agent.runtime) or "")  # consumed


class TestPrimaryGoalFrozen:
    """A (2026-08-21): the primary goal never flips mid-call; other mentions
    become secondary problems (asked at the end, listed on the ticket)."""

    def test_mid_call_mention_becomes_secondary(self, db_connection):
        from tests.calls import hear, make_agent

        agent = make_agent("unknown")
        s = agent.state
        hear(agent, "Neveikia internetas")
        assert s.intake.problem_type == "internet_down"
        s.identity.customer_id = "CUST009"
        s.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        hear(agent, "O dar televizorius man blogai rodo")
        assert s.intake.problem_type == "internet_down"  # frozen
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"
        # dedupe: the same type mentioned again does not duplicate
        hear(agent, "Tas televizorius vis dar blogai")
        assert len(s.intake.secondary_problems) == 1
        # A request type (billing, D-11) never becomes a secondary TECH problem —
        # it is not a fault to list on the fault ticket.
        hear(agent, "O dar sąskaitos klausimas turiu")
        assert all(x["type"] != "billing" for x in s.intake.secondary_problems)

    def test_secondary_lands_on_ticket_and_closing_facts(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        s = agent.state
        s.identity.customer_id = "CUST009"
        s.intake.problem_type = "internet_down"
        s.intake.secondary_problems.append({"type": "tv", "text": "TV blogai rodo", "turn": 5})
        s.closing.case_closed = True
        block = context_card(agent.state, agent.runtime)
        assert "SECONDARY PROBLEMS" in block and "TV blogai rodo" in block

    def test_bridge_bound_phrase_states_visibility(self):
        from agent.contract.locale import phrase

        text = phrase("identification.bridge_bound")
        assert "matau" in text.lower() and "pririšau" in text.lower()


class TestOpenerAndClosingHygiene:
    """Live 2026-08-21: a garbled opener triggered the address offer before
    any problem; a garble in the ticket dialogue became a 'secondary problem';
    the closing LLM re-asked the hours after registration."""

    def test_garbled_opener_asks_for_the_problem(self, db_connection):
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        agent = make_agent("unknown")
        r1 = scripted_words(agent.state, agent.runtime, "Atsikai, daro.")
        assert r1 and "problema" in r1
        r2 = scripted_words(agent.state, agent.runtime, "Mmm kažkas.")
        assert r2 and "problema" in r2
        # scripted mode (NARRATOR_QUESTIONS=off in tests): keeps asking, then
        # the gate closes politely on the 5th attempt
        assert "problema" in scripted_words(agent.state, agent.runtime, "Nu...")
        assert "problema" in scripted_words(agent.state, agent.runtime, "Eee...")
        bye = scripted_words(agent.state, agent.runtime, "Mmm.")
        assert bye and "skambinkite" in bye

    def test_phone_account_block_waits_for_the_problem(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.phone_candidate = {
            "customer_id": "CUST009",
            "name": "T",
            "address": "Šiauliai, Vilniaus g. 29",
            "street": "Vilniaus g.",
            "house": "29",
            "apartment": None,
            "city": "Šiauliai",
        }
        assert "PHONE ACCOUNT" not in (context_card(agent.state, agent.runtime) or "")
        agent.state.intake.problem_type = "internet_down"
        assert "PHONE ACCOUNT" in (context_card(agent.state, agent.runtime) or "")

    def test_no_secondary_problems_from_ticket_stage_garbles(self, db_connection):
        from tests.calls import hear, make_agent

        agent = make_agent("unknown")
        s = agent.state
        s.intake.problem_type = "internet_down"
        s.identity.customer_id = "CUST009"
        s.resolution.procedure = {"verdict": "no_mac_observed", "step": "escalate"}
        agent.state.ticket.stage = "hours"
        hear(agent, "Sąskaitos žemės gatvės klausimas")
        assert s.intake.secondary_problems == []
        agent.state.ticket.stage = None
        hear(agent, "Žemės gatvės")  # 2 words: a garble
        assert s.intake.secondary_problems == []
        hear(agent, "O dar televizorius man blogai rodo")
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"


class TestD5WaitAckAndClosing:
    """D5 (live 2026-08-25): scripted wait acknowledgements (the LLM cost up
    to 12 s for 'Gerai, palauksiu') and the closing fixes — the scripted
    goodbye must SPEAK, and a post-registration number correction must land
    on the ticket instead of vanishing."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_pick_cable"}
        return agent

    def test_wait_signal_gets_scripted_ack(self, db_connection):
        from agent.decide.rules.dialog import scripted_wait_ack
        from agent.perceive.detectors import INTENT_IN_PROGRESS

        agent = self._agent()
        agent.state.dialog.last_intent = INTENT_IN_PROGRESS
        agent.state.dialog.awaiting = "client_action"
        agent.state.dialog.awaiting_turns = 1
        assert (
            scripted_wait_ack(agent.state, agent.runtime)
            == "Gerai, lauksiu — pasakykite, kai būsite pasiruošę."
        )
        agent.state.dialog.awaiting_turns = 2
        assert scripted_wait_ack(agent.state, agent.runtime) == "Gerai, neskubėkite."

    def test_wait_ack_defers_to_directives_and_other_intents(self, db_connection):
        from agent.decide.rules.dialog import scripted_wait_ack
        from agent.perceive.detectors import INTENT_IN_PROGRESS

        agent = self._agent()
        agent.state.dialog.last_intent = INTENT_IN_PROGRESS
        agent.state.dialog.awaiting = "client_action"
        agent.state.turn.directives.evidence = {"reikia": "x"}
        assert scripted_wait_ack(agent.state, agent.runtime) is None
        agent.state.turn.directives.evidence = None
        agent.state.dialog.last_intent = "answer"
        assert scripted_wait_ack(agent.state, agent.runtime) is None

    def test_closing_goodbye_is_spoken_and_number_correction_lands(self, db_connection):
        from types import SimpleNamespace

        from agent.tools import create_ticket
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        agent = self._agent()
        res = create_ticket("CUST009", "network_issue", "routeris nedega")
        assert res.get("success")
        agent.state.ticket.ticket_id = res["ticket_id"]
        agent.state.closing.case_closed = True
        runtime = Runtime(context=agent.runtime)
        # 1) number correction: acknowledged aloud AND noted on the ticket
        upd = run_turn_nodes(
            agent.state.model_copy(
                update={"turn": TurnScratch(user_input="Skambinkite kitu numeriu 868321007")}
            ),
            runtime,
        )
        assert "Užsirašiau" in upd["turn"].reply
        assert upd["messages"][-1]["content"] == upd["turn"].reply
        agent.state = GraphState(**upd)  # the next turn starts from the committed state
        import sqlite3

        from agent.tools import get_db

        with get_db().cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "PATIKSLINTA" in details and "868321007" in details
        # 2) a plain 'gerai' now gets the SPOKEN scripted goodbye
        upd2 = run_turn_nodes(
            agent.state.model_copy(update={"turn": TurnScratch(user_input="Gerai, ačiū")}), runtime
        )
        assert upd2["turn"].reply and "Geros dienos" in upd2["turn"].reply
        assert upd2["messages"][-1]["content"] == upd2["turn"].reply
