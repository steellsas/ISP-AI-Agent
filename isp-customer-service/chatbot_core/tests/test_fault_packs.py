"""
Fault packs (R5) — one file per fault + reusable modules + meta/tags.

The heart is the EQUIVALENCE test: the split pack files with module calls must
build byte-identical Strategy structures to the pre-split monolith (snapshot in
tests/data/strategies_snapshot.json, captured before the migration). If a pack
edit changes the tree, the snapshot must be updated DELIBERATELY.
"""

import json
from pathlib import Path

from agent.faults import (
    _modules,
    build_strategy,
    depends_on,
    fault_meta,
    find_by_tag,
    step_options,
)

_SNAPSHOT = json.loads(
    (Path(__file__).parent / "data" / "strategies_snapshot.json").read_text(encoding="utf-8-sig")
)


def _dump(strat):
    return {
        "rag_doc": strat.rag_doc,
        "steps": [
            {
                "id": s.id,
                "kind": s.kind.value,
                "detector": s.detector,
                "on": dict(s.on),
                "goto": s.goto,
                "tools": sorted(s.tools),
                "tool_actions": list(s.tool_actions),
                "rag_section": s.rag_section,
                "consent": s.consent,
            }
            for s in strat.steps
        ],
    }


class TestEquivalence:
    """Split packs + expanded modules == the pre-split monolith, structurally."""

    def test_foreign_mac_matches_snapshot(self):
        assert _dump(build_strategy("foreign_mac")) == _SNAPSHOT["foreign_mac"]

    def test_healthy_to_router_matches_snapshot(self):
        assert _dump(build_strategy("healthy_to_router")) == _SNAPSHOT["healthy_to_router"]

    def test_no_mac_observed_matches_snapshot(self):
        assert _dump(build_strategy("no_mac_observed")) == _SNAPSHOT["no_mac_observed"]

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
        assert "patikrinti_ar_atsirado" in mods
        assert "priristi_mac" in mods
        assert mods["patikrinti_ar_atsirado"]["isejimai"] == ["pavyko", "nepavyko"]

    def test_meta_and_tags(self):
        meta = fault_meta("no_mac_observed")
        assert meta.get("domenas") == "internet"
        assert "tiltas" in meta.get("tags", [])
        by_tag = find_by_tag("nera_interneto")
        assert set(by_tag) == {"foreign_mac", "healthy_to_router", "no_mac_observed"}

    def test_depends_on_default_empty(self):
        assert depends_on("foreign_mac") == []
        assert depends_on("nezinomas") == []


class TestSolverMechanics:
    """R4b mechanics — pack-declared driver + the walker solution kind. The
    packs themselves stay walker-driven until each is flipped deliberately."""

    def test_all_packs_declare_solver_driver(self):
        # R4b flip (Andrius 2026-08-13: visus iš karto, tada testuojam)
        from agent.faults import driver

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            assert driver(verdict) == "solveris"

    def test_walker_solution_syncs_step_and_hands_over(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.evidence_drive import evidence_drive

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "walker")
        monkeypatch.setattr(ev, "solution_step", lambda e, v: "bind_mac")

        gotos = []
        engine = SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "x", "step": "a"}, evidence={}, turn_count=1
            ),
            _findings_announced=True,
            _evidence_last_ask_key=None,
            _evidence_asks={},
            _goto_step=lambda r, t: gotos.append(t),
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        assert evidence_drive(engine, "taip") is None  # walker takes the turn
        assert gotos == ["bind_mac"]


class TestVoiceTestFixes:
    """2026-08-13 live-call fixes: polarity, early facts, phase gating, glosses."""

    def test_negated_demand_is_not_a_demand(self):
        from agent.resolution import detect_refuse_or_ticket

        assert detect_refuse_or_ticket("Neregistruokite, pajunkim kompiuterį") != "demand"
        assert detect_refuse_or_ticket("užregistruokit gedimą") == "demand"

    def test_demand_with_stop_words_keeps_the_dialogue(self):
        from types import SimpleNamespace

        from agent.ticket_flow import wants_to_keep_solving

        engine = SimpleNamespace()
        # live phrase: negated solving verbs + explicit demand -> NOT keep-solving
        assert (
            wants_to_keep_solving(
                engine, "Nebe noriu tikrinti toliau, užregistruokit gedimą ir nebesprendžiam"
            )
            is False
        )
        assert wants_to_keep_solving(engine, "Ne, pajunkim tą kompiuterį") is True

    def test_aciu_nereikia_is_a_farewell(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Ačiū, nereikia") is True
        assert detect_farewell("Nebereikia.") is True
        assert detect_farewell("Ačiū") is False

    def test_anamnesis_seeds_ledger_on_activation(self):
        from types import SimpleNamespace

        from agent.walker_flow import _seed_evidence_from_anamnesis

        engine = SimpleNamespace(
            state=SimpleNamespace(
                anamnesis_raw="Ką kečiau, routere?",
                resolution={"verdict": "foreign_mac", "step": "confirm_change"},
                evidence={},
                turn_count=1,
            ),
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        _seed_evidence_from_anamnesis(engine)
        assert engine.state.evidence.get("changed_device", {}).get("value") == "keite"

    def test_pack_glosses_replace_raw_keys(self):
        from agent.evidence import gloss_label, gloss_value

        assert gloss_label("changed_device") == "routerio keitimas"
        assert gloss_value("keite") == "keitė arba prijungė naują įrenginį"
        assert gloss_label("lights") == "routerio lemputės"  # built-ins keep working


class TestNarratorWordedQuestions:
    """Persona (R5c): the first ask becomes a narrator GOAL directive; retries
    and formuluote:skriptas stay scripted; off-switch reverts everything."""

    def _engine(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "no_mac_observed", "step": "dr_intro"},
                evidence={},
                turn_count=1,
            ),
            _findings_announced=True,
            _recap_state="done",
            _evidence_last_ask_key=None,
            _evidence_asks={},
            _evidence_directive=None,
            _pending_announce="",
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )

    def test_first_ask_delegates_to_narrator(self, monkeypatch):
        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        engine = self._engine()
        assert evidence_drive(engine, "labas") is None
        d = engine._evidence_directive
        assert d and d["key"] == "device_present" and d["reikia"]
        assert engine._evidence_asks["device_present"] == 1  # ask bookkeeping intact

    def test_off_switch_keeps_scripted_wording(self, monkeypatch):
        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        engine = self._engine()
        reply = evidence_drive(engine, "labas")
        assert reply and "Susiraskite routerį" in reply
        assert engine._evidence_directive is None

    def test_directive_lands_in_facts_block(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._evidence_directive = {
            "key": "lights",
            "reikia": "ar dega bent viena lemputė",
            "kodel": "matysime ar gauna srovę",
            "klausimas": "Ar dega lemputė?",
        }
        block = agent._state_facts_block()
        assert block and "KLAUSK DABAR" in block and "ar dega bent viena lemputė" in block


class TestNarratorFindings:
    """Persona (2026-08-13, dead-router live call): the findings announce was a
    template dump ('routeris surastas: rado; lemputės: nedega...') — words FOR
    the agent, not speech. In narrator mode the findings become a GOAL
    directive; the off-switch keeps the scripted announce."""

    def _engine(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "no_mac_observed", "step": "dr_intro"},
                evidence={},
                turn_count=3,
            ),
            _findings_announced=False,
            _recap_state="done",
            _evidence_last_ask_key=None,
            _evidence_asks={},
            _evidence_directive=None,
            _findings_directive=None,
            _pending_announce="",
            _ticket_need=lambda: "",
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )

    def _mock_confirmed(self, monkeypatch):
        from agent import evidence as ev

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        monkeypatch.setattr(ev, "fault_isvada", lambda v: "routeris sugedęs")
        monkeypatch.setattr(
            ev, "solution_descriptions", lambda v: ["paleisti per kompiuterį", "meistras"]
        )
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "bridge")

    def test_anamnesis_followup_ladder(self, db_connection):
        """E (2026-08-20): 'nežinau' -> ask when it last WORKED -> the answer
        lands as anamnesis_when and the ladder proceeds to the address."""
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        s = agent.state
        s.problem_type = "internet_down"
        s.anamnesis_asked = True
        reply = agent._identification_scripted_reply("Nežinau, nepastebėjau.")
        assert reply and "paskutinį kartą" in reply
        reply2 = agent._identification_scripted_reply("Vakar lyg viskas veikė.")
        assert reply2 and ("adres" in reply2.lower())
        assert s.anamnesis_when and "vakar" in s.anamnesis_when.lower()
        assert "paskutinį kartą veikė" in (s.anamnesis_raw or "")

    def test_wait_signal_holds_instead_of_reasking(self, monkeypatch):
        """C (2026-08-20): 'palaukit, ateinu' -> Gerai, lauksiu; no retry burn."""
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: None)
        monkeypatch.setattr(
            ev,
            "next_missing",
            lambda e, s, c: ("device_present", {"klausimas": "Radote routerį?"}),
        )
        engine = SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "no_mac_observed", "step": "dr_intro"},
                evidence={},
                turn_count=2,
            ),
            _findings_announced=False,
            _recap_state="done",
            _recap_directive=None,
            _evidence_last_ask_key="device_present",
            _evidence_asks={"device_present": 1},
            _evidence_directive=None,
            _pending_announce="",
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        reply = evidence_drive(engine, "Palaukit, tuoj ateinu.")
        assert reply and "lauksiu" in reply.lower()
        assert engine._evidence_asks["device_present"] == 1  # retry NOT burned

    def test_reask_phrase_has_no_internal_labels(self):
        from agent.identification import phrase

        text = phrase("reask_reason", tema="routeris surastas", klausimas="Radote?")
        assert "routeris surastas" not in text and "Radote?" in text

    def test_phone_echo_is_consent(self, monkeypatch):
        """D (2026-08-20): the caller echoing our own phone offer is a yes."""
        from agent.barge_in import token_overlap

        q = "Ar tiks numeris, iš kurio skambinate? — ar tiks tas, iš kurio skambinate?"
        assert token_overlap("Ar tiks tas, iš kurio skambinu?", q) >= 0.8
        assert token_overlap("O kiek kainuoja meistras?", q) < 0.8

    def test_recap_delegates_to_narrator(self, monkeypatch):
        from agent.evidence_drive import maybe_facts_recap

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        from types import SimpleNamespace

        engine = SimpleNamespace(
            state=SimpleNamespace(evidence={"lights": {"value": "nedega", "source": "client"}}),
            _recap_state="",
            _recap_directive=None,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        from agent import evidence as ev

        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        assert maybe_facts_recap(engine) is None
        assert engine._recap_directive and "nedega" in engine._recap_directive["faktai"]
        assert engine._recap_state == "pending"

    def test_recap_off_switch_stays_scripted(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.evidence_drive import maybe_facts_recap

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        engine = SimpleNamespace(
            state=SimpleNamespace(evidence={"x": {}}),
            _recap_state="",
            _recap_directive=None,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        reply = maybe_facts_recap(engine)
        assert reply and "Pasitikslinu" in reply and engine._recap_directive is None

    def test_recap_directive_lands_in_facts_block(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._recap_directive = {"faktai": "routerio lemputės: nedega"}
        block = agent._state_facts_block()
        assert "PASITIKSLINK" in block and "nedega" in block

    def test_findings_delegate_to_narrator(self, monkeypatch):
        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        self._mock_confirmed(monkeypatch)
        engine = self._engine()
        assert evidence_drive(engine, "nedega") is None  # narrator takes the turn
        d = engine._findings_directive
        assert d and d["isvada"] == "routeris sugedęs"
        assert "ARBA" in d["sprendimai"]
        assert engine._findings_announced is True  # said once, never re-dumped

    def test_off_switch_keeps_scripted_announce(self, monkeypatch):
        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        self._mock_confirmed(monkeypatch)
        engine = self._engine()
        assert evidence_drive(engine, "nedega") is None  # bridge -> solver drives
        assert engine._findings_directive is None
        assert "Ką patikrinome" in engine._pending_announce

    def test_findings_directive_lands_in_facts_block(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._findings_directive = {
            "faktai": "routerio lemputės: nedega",
            "isvada": "routeris sugedęs",
            "sprendimai": "paleisti per kompiuterį ARBA meistras",
        }
        block = agent._state_facts_block()
        assert block and "IŠVADOS MOMENTAS" in block and "routeris sugedęs" in block
        assert "Pasiūlyk pasirinkimą" in block

    def test_bridge_anchor_lands_in_narrator_facts(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._bridge_plug_reported = True
        block = agent._state_facts_block()
        assert block and "TILTO FAZĖ" in block and "NEBEKLAUSK" in block


class TestTicketFirst:
    """2026-08-13 live call: the dead router NEEDS a registration — the bridge
    is a convenience. Solver 'close' may not skip the ticket; a demand is
    never a side topic; the goodbye hears the demand too."""

    def test_garbled_demands_are_demands(self):
        from agent.resolution import detect_refuse_or_ticket

        assert detect_refuse_or_ticket("Išregistruoti meistrą ir paleisti internetą") == "demand"
        assert detect_refuse_or_ticket("Dar prašau, žegistruokit gedimą") == "demand"
        assert detect_refuse_or_ticket("Neregistruokite, bandome toliau") != "demand"

    def test_infinitive_needs_intent(self):
        """Live 2026-08-14: small talk with the bare infinitive escalated
        mid-collection and the findings moment never happened."""
        from agent.resolution import detect_refuse_or_ticket

        assert (
            detect_refuse_or_ticket(
                "O jums dažnai taip skamina gedimus? Registruoti. Gerai, padariau tai."
            )
            is None
        )
        assert detect_refuse_or_ticket("Noriu registruoti gedimą") == "demand"
        assert detect_refuse_or_ticket("Gal galite užregistruoti meistrą?") == "demand"

    def test_demand_is_never_a_side_topic(self):
        from types import SimpleNamespace

        from agent.perception_flow import classify_side_topic

        engine = SimpleNamespace(
            state=SimpleNamespace(customer_id="C1", case_closed=False),
            _ticket_stage=None,
            _evidence_conflict=None,
            _end_confirm_pending=False,
            _resume_hold=False,
            _side_topic_this_turn=False,
            _side_topic_turns=0,
            _last_understanding={"tipas": "nukrypimas", "faktai": {}},
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        assert classify_side_topic(engine, "Išregistruoti meistrą ir paleisti internetą") is False
        assert engine._side_topic_this_turn is False

    def test_solver_close_after_bridge_registers(self):
        from types import SimpleNamespace

        from agent.solver_flow import close_or_register

        calls = []
        engine = SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "no_mac_observed", "telemetry_fixed": True},
                ticket_id=None,
                case_closed=False,
                closed_reason=None,
            ),
            _bridge_bound=True,
            _drive_escalate=lambda d: calls.append("escalate") or "Užregistruosiu gedimą…",
            _settle_hypothesis=lambda *a, **k: None,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        reply = close_or_register(engine, "Puiku!")
        assert calls == ["escalate"] and "gedim" in reply
        assert engine.state.case_closed is False  # the dialogue closes it later

    def test_solver_close_without_bridge_stays_a_close(self):
        from types import SimpleNamespace

        engine = SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "x"}, ticket_id=None, case_closed=False, closed_reason=None
            ),
            _bridge_bound=False,
            _settle_hypothesis=lambda *a, **k: None,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        from agent.solver_flow import close_or_register

        assert "Puiku" in close_or_register(engine, "")
        assert engine.state.case_closed is True

    def test_pack_declares_ticket_first_offer(self):
        from agent.evidence import fault_pasiulymas

        text = fault_pasiulymas("no_mac_observed")
        assert text and "meistr" in text and "kompiuter" in text

    def test_open_goals_follow_the_ledger(self):
        from agent.evidence import CLIENT, open_goals_lt

        assert "surado routerį" in open_goals_lt({}, "no_mac_observed")
        ev = {
            "device_present": {"value": "rado", "source": CLIENT, "turn": 1},
            "lights": {"value": "nedega", "source": CLIENT, "turn": 2},
        }
        goals = open_goals_lt(ev, "no_mac_observed")
        assert "maitinimo laidas" in goals and "surado routerį" not in goals
        # kada-gated keys stay hidden until eligible; engine-only gates never show
        assert "kompiuter" not in goals and "LAN" not in goals

    def test_situational_block_lands_in_narrator_facts(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST001"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_intro"}
        block = agent._state_facts_block()
        assert block and "DAR AIŠKINAMĖS" in block and "grąžink" in block

    def test_findings_prefer_the_pack_offer(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._findings_directive = {
            "faktai": "routerio lemputės: nedega",
            "isvada": "routeris sugedęs",
            "sprendimai": "a ARBA b",
            "pasiulymas": "Pasakyk, kad užregistruosi meistrą; pasiūlyk tiltą.",
        }
        block = agent._state_facts_block()
        assert "užregistruosi meistrą" in block
        assert "Pasiūlyk pasirinkimą" not in block


class TestStepAwareness:
    """VOICE_PLAN 1 žingsnis (L1+L2): one question per turn, the step's goal
    (`tikslas`) drives evaluative reactions, repeats come with an explanation,
    and the solver reads the walked path from the journal."""

    def test_caller_question_is_single(self):
        from pathlib import Path

        import yaml

        data = yaml.safe_load(
            (
                Path(__file__).parents[1] / "src" / "agent" / "knowledge" / "identification.yaml"
            ).read_text(encoding="utf-8")
        )
        q = data["identification"]["questions"]["caller"]
        assert q.count("?") == 1 and "sudar" not in q

    def test_tikslas_flows_through_build(self):
        from agent.faults import build_strategy

        strat = build_strategy("no_mac_observed")
        by_id = {st.id: st for st in strat.steps}
        assert "sutinka" in by_id["dr_intro"].tikslas
        assert "lemput" in by_id["dr_lights"].tikslas
        # module instance override (kaip: dr_verify) carries its own goal
        assert "kompiuteryje internetas" in by_id["dr_verify"].tikslas

    def test_goto_step_writes_the_journal(self):
        from types import SimpleNamespace

        from agent.walker_flow import goto_step

        engine = SimpleNamespace(tracer=SimpleNamespace(emit=lambda *a, **k: None))
        r = {"step": "dr_intro"}
        goto_step(engine, r, "dr_lights")
        goto_step(engine, r, "dr_lights")  # same step -> no duplicate entry
        goto_step(engine, r, "dr_power")
        assert r["journal"] == ["dr_intro→dr_lights", "dr_lights→dr_power"]

    def test_facts_block_states_goal_and_repeat(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST001"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 2},
        }
        block = agent._state_facts_block()
        assert "ŠIO ŽINGSNIO TIKSLAS" in block and "lemput" in block
        assert "ŽINGSNIS KARTOJAMAS" in block

    def test_first_presentation_has_no_repeat_directive(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST001"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 1},
        }
        block = agent._state_facts_block()
        assert "ŽINGSNIS KARTOJAMAS" not in block

    def test_solver_context_includes_the_journey(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST001"
        agent.state.resolution = {
            "verdict": "no_mac_observed",
            "step": "dr_power",
            "journal": ["dr_intro→dr_lights", "dr_lights→dr_power"],
        }
        ctx = agent._build_solver_context("nedega")
        assert "ŽINGSNIŲ EIGA" in ctx and "dr_intro→dr_lights" in ctx


class TestEvidenceDeclared:
    """A variantas (2026-08-13): every internet pack declares its analysis
    knowledge — the perception vocabulary and the hypothesis logic."""

    def test_all_three_packs_have_evidence(self):
        from agent.evidence import spec_for

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            spec = spec_for(verdict)
            assert spec is not None, verdict
            assert spec.get("client"), verdict

    def test_foreign_mac_facts_and_confirmation(self):
        from agent.evidence import spec_for

        spec = spec_for("foreign_mac")
        assert set(spec["client"]) == {"changed_device", "cable_port"}
        # hypothesis is a TELEMETRY fact — confirmed from the start; client
        # facts pick the SOLUTION (sprendimai), not the hypothesis
        assert spec["patvirtinta_kai"] == []
        # perception vocabulary: canonical values are declared per fact
        assert set(spec["client"]["changed_device"]["atsakymai"]) == {"keite", "nekeite"}

    def test_healthy_to_router_conditional_asking(self):
        from agent.evidence import spec_for

        spec = spec_for("healthy_to_router")
        assert spec["client"]["connection_type"]["kada"] == ["fail_device=kompiuteris"]
        assert spec["client"]["rebooted"]["kada"] == ["fail_scope=visuose"]

    def test_reikia_present_for_narrator_directives(self):
        """`reikia` is the future narrator directive (skriptas -> mąstymas) —
        every declared fact must state its GOAL, not only the wording."""
        from agent.evidence import spec_for

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            for key, item in spec_for(verdict)["client"].items():
                assert item.get("reikia"), f"{verdict}.{key} be 'reikia'"


class TestIdentificationF:
    """F (2026-08-20): identifikacija kaip pokalbis — pasakyk, ką radai ir ko
    ne; paragink su KODĖL; nesėkmę užfiksuok įraše."""

    def test_diag_street_found_house_not(self):
        from agent.identification_flow import address_diag_note

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
        from agent.identification_flow import address_diag_note

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
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent._addr_diag_note = "- ADRESO PAIEŠKOS DIAGNOZĖ: gatvę RANDU, namo NĖRA."
        block = agent._state_facts_block()
        assert block and "ADRESO PAIEŠKOS DIAGNOZĖ" in block

    def test_encouragement_appears_once(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        agent.state.turn_count = 5
        first = agent._state_facts_block() or ""
        second = agent._state_facts_block() or ""
        assert "PARAGINIMAS DĖL ADRESO" in first
        assert "PARAGINIMAS DĖL ADRESO" not in second

    def test_failed_identification_lands_on_the_record(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        agent.state.heard_utterances.extend(["neveikia internetas", "Vilnaus gatve kazkur"])
        summary = agent._build_call_summary()
        fail = summary["identifikacija_nepavyko"]
        assert fail and "Vilnaus gatve kazkur" in fail["girdeta"]

    def test_short_ladder_phrases(self):
        from agent.identification import phrase

        assert phrase("address_ask") == "Gerai — patikrinsiu ryšį iki jūsų buto. Koks adresas?"
        assert "patikrinsiu ryšį" in phrase("address_offer", adresas="X")


class TestTicketDirectives:
    """Zone 1 (skriptai -> direktyvos): the ticket dialogue's question moments
    become narrator goal directives; retries/cancel stay scripted; off reverts."""

    def _agent(self, db_connection=None):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "escalate"}
        agent._ticket_stage = "phone"
        agent._ticket_ctx = {"step": None}
        return agent

    def test_phone_intro_goes_to_narrator(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        reply = agent._identification_scripted_reply("nepatogu, ne namuose")
        assert reply is None  # the narrator takes the turn
        td = agent._ticket_directive
        assert td and td["kind"] == "phone_intro" and "numeris" in td["fallback"]
        block = agent._state_facts_block()
        assert "TIKETO ŽINGSNIS" in block and "registruoji meistrą" in block

    def test_off_switch_keeps_scripted(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = self._agent()
        reply = agent._identification_scripted_reply("gerai")
        assert reply and "Ar tiks numeris" in reply
        assert agent._ticket_directive is None

    def test_retry_stays_scripted_even_in_narrator_mode(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        agent._ticket_ctx["ask_retry"] = "phone"
        reply = agent._identification_scripted_reply("kazkas neaisku")
        assert reply and "skaitmenimis" in reply  # precision repeat, no LLM
        assert agent._ticket_directive is None

    def test_hours_directive(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        agent._ticket_stage = "hours"
        agent._ticket_ctx = {"step": None, "intro_done": True}
        assert agent._identification_scripted_reply("tiks tas") is None
        assert agent._ticket_directive["kind"] == "hours"
        assert "patogiausia" in agent._state_facts_block()


class TestIdentDirectives:
    """Zone 2: the transition to the address becomes a narrator goal directive;
    the OFFER question core stays verbatim (confirm guard); off reverts."""

    def _agent(self, candidate=True):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        if candidate:
            agent.state.phone_candidate = {
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
        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent()
        reply = agent._identification_scripted_reply("Vakar po audros dingo")
        assert reply is None
        idd = agent._ident_directive
        assert idd and idd["kind"] == "address_offer" and "Vilniaus g. 29" in idd["adresas"]
        block = agent._state_facts_block()
        assert "Ar skambinate dėl Vilniaus g. 29?" in block  # verbatim core kept

    def test_ask_goes_to_narrator_without_candidate(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = self._agent(candidate=False)
        assert agent._identification_scripted_reply("Vakar po audros dingo") is None
        assert agent._ident_directive["kind"] == "address_ask"
        assert "IDENTIFIKACIJOS ŽINGSNIS" in agent._state_facts_block()

    def test_off_switch_keeps_scripted_offer(self, db_connection, monkeypatch):
        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = self._agent()
        reply = agent._identification_scripted_reply("Vakar po audros dingo")
        assert reply and "Ar skambinate dėl Vilniaus g. 29?" in reply
        assert agent._ident_directive is None


class TestAnamnesisDirectives:
    """Zone 3: the anamnesis questions go to the narrator (adaptive wording);
    the capture ladder and the follow-up rung mechanics stay deterministic."""

    def test_anamnesis_goes_to_narrator(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        assert agent._identification_scripted_reply("Neveikia internetas") is None
        assert agent.state.anamnesis_asked is True  # the flag still set
        assert agent._ident_directive["kind"] == "anamnesis"
        assert "ANAMNEZĖS ŽINGSNIS" in agent._state_facts_block()

    def test_followup_goes_to_narrator(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        agent.state.anamnesis_asked = True
        assert agent._identification_scripted_reply("Nežinau, nepastebėjau") is None
        assert agent._ident_directive["kind"] == "anamnesis_followup"
        assert "TIKRAI veikė" in agent._state_facts_block()

    def test_off_switch_keeps_scripted_anamnesis(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = ReactAgent(caller_phone="unknown")
        agent.state.problem_type = "internet_down"
        reply = agent._identification_scripted_reply("Neveikia internetas")
        assert reply and "kada dingo" in reply
        assert agent._ident_directive is None


class TestDirectiveTurnsAreSpeechOnly:
    """Live 2026-08-20: with tools exposed the model grabbed resolve_address on
    the anamnesis directive turn and skipped the ladder — directive turns get
    NO tools; the engine owns the mechanics."""

    def test_no_tools_when_directive_set(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        assert agent._scoped_tools_schema()  # baseline: tools exist
        agent._ident_directive = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        assert agent._scoped_tools_schema() == []
        agent._ident_directive = None
        agent._ticket_directive = {"kind": "hours", "fallback": "x"}
        assert agent._scoped_tools_schema() == []


class TestDetourResilience:
    """Live 2026-08-20: a bare 'Ne.' read as farewell derailed the recap ->
    findings chain and the agent re-ran diagnostics it already had."""

    def test_bare_ne_is_never_a_farewell(self):
        from agent.resolution import detect_farewell

        assert detect_farewell("Ne.") is False
        assert detect_farewell("Ne") is False
        assert detect_farewell("Ne, ačiū") is True  # real closer kept
        assert detect_farewell("Viso gero") is True

    def test_split_ne_symptom_polarity(self):
        from agent.nlu import extract_symptoms

        assert extract_symptoms("Ne 1 lemputė ne dega.").get("lights") == "nedega"
        assert extract_symptoms("lemputės nedega").get("lights") == "nedega"

    def test_resync_note_renders_once(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights"}
        from agent.evidence import CLIENT, set_fact

        set_fact(agent.state.evidence, "lights", "nedega", CLIENT, 1)
        agent._resync_note = True
        block = agent._state_facts_block()
        assert "GRĮŽTAME PRIE SPRENDIMO" in block and "nustatyta" in block
        assert "GRĮŽTAME" not in (agent._state_facts_block() or "")  # consumed


class TestPrimaryGoalFrozen:
    """A (2026-08-21): the primary goal never flips mid-call; other mentions
    become secondary problems (asked at the end, listed on the ticket)."""

    def test_mid_call_mention_becomes_secondary(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        s = agent.state
        agent._prefill_slots_from_text("Neveikia internetas")
        assert s.problem_type == "internet_down"
        s.customer_id = "CUST009"
        s.resolution = {"verdict": "no_mac_observed", "step": "dr_intro"}
        agent._prefill_slots_from_text("O dar sąskaitos klausimas turiu")
        assert s.problem_type == "internet_down"  # frozen
        assert s.secondary_problems and s.secondary_problems[0]["tipas"] == "billing"
        # dedupe: the same type mentioned again does not duplicate
        agent._prefill_slots_from_text("Dėl sąskaitos dar")
        assert len(s.secondary_problems) == 1

    def test_secondary_lands_on_ticket_and_closing_facts(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        s = agent.state
        s.customer_id = "CUST009"
        s.problem_type = "internet_down"
        s.secondary_problems.append({"tipas": "tv", "tekstas": "TV blogai rodo", "turn": 5})
        s.case_closed = True
        block = agent._state_facts_block()
        assert "PAPILDOMOS PROBLEMOS" in block and "TV blogai rodo" in block

    def test_bridge_bound_phrase_states_visibility(self):
        from agent.identification import phrase

        text = phrase("bridge_bound")
        assert "matau" in text.lower() and "pririšau" in text.lower()


class TestWalkerFollowsLedger:
    """B2 (Andrius 2026-08-21): one source of truth — in solver-driven packs the
    walker reads no answers until the evidence layer hands over; facts may
    carry a `zingsnis` pointer so RAG/hint/tikslas follow the ledger."""

    def test_walker_silent_during_evidence_collection(self):
        from types import SimpleNamespace

        from agent.resolution import get_strategy
        from agent.walker_flow import walker_owns_turn

        strat = get_strategy("no_mac_observed")
        engine = SimpleNamespace(_bridge_bound=False)
        r = {"verdict": "no_mac_observed", "step": "dr_lights"}
        assert walker_owns_turn(engine, r, strat.step("dr_lights")) is False
        assert walker_owns_turn(engine, r, strat.step("escalate")) is True
        assert walker_owns_turn(engine, r, strat.step("dr_see_device")) is True
        r["solution_synced"] = "dr_plug_pc"
        assert walker_owns_turn(engine, r, strat.step("dr_plug_pc")) is True
        engine._bridge_bound = True
        del r["solution_synced"]
        assert walker_owns_turn(engine, r, strat.step("dr_verify")) is True

    def test_fact_pointer_moves_the_walker(self, monkeypatch):
        from types import SimpleNamespace

        from agent.evidence_drive import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        gotos = []
        engine = SimpleNamespace(
            state=SimpleNamespace(
                resolution={"verdict": "no_mac_observed", "step": "dr_intro"},
                evidence={},
                turn_count=1,
            ),
            _findings_announced=True,
            _recap_state="done",
            _recap_directive=None,
            _evidence_last_ask_key=None,
            _evidence_asks={},
            _evidence_directive=None,
            _pending_announce="",
            _goto_step=lambda r, t: (gotos.append(t), r.__setitem__("step", t)),
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        reply = evidence_drive(engine, "labas")
        assert reply and "routerį" in reply  # first fact asked (device_present)
        assert gotos == ["dr_lights"]  # pointer followed the fact


class TestOpenerAndClosingHygiene:
    """Live 2026-08-21: a garbled opener triggered the address offer before
    any problem; a garble in the ticket dialogue became a 'secondary problem';
    the closing LLM re-asked the hours after registration."""

    def test_garbled_opener_asks_for_the_problem(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        r1 = agent._identification_scripted_reply("Atsikai, daro.")
        assert r1 and "problema" in r1
        r2 = agent._identification_scripted_reply("Mmm kažkas.")
        assert r2 and "problema" in r2
        # scripted mode (NARRATOR_QUESTIONS=off in tests): keeps asking, then
        # the gate closes politely on the 5th attempt
        assert "problema" in agent._identification_scripted_reply("Nu...")
        assert "problema" in agent._identification_scripted_reply("Eee...")
        bye = agent._identification_scripted_reply("Mmm.")
        assert bye and "skambinkite" in bye

    def test_phone_account_block_waits_for_the_problem(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.phone_candidate = {
            "customer_id": "CUST009",
            "name": "T",
            "address": "Šiauliai, Vilniaus g. 29",
            "street": "Vilniaus g.",
            "house": "29",
            "apartment": None,
            "city": "Šiauliai",
        }
        assert "PHONE ACCOUNT" not in (agent._state_facts_block() or "")
        agent.state.problem_type = "internet_down"
        assert "PHONE ACCOUNT" in (agent._state_facts_block() or "")

    def test_no_secondary_problems_from_ticket_stage_garbles(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        s = agent.state
        s.problem_type = "internet_down"
        s.customer_id = "CUST009"
        s.resolution = {"verdict": "no_mac_observed", "step": "escalate"}
        agent._ticket_stage = "hours"
        agent._prefill_slots_from_text("Sąskaitos žemės gatvės klausimas")
        assert s.secondary_problems == []
        agent._ticket_stage = None
        agent._prefill_slots_from_text("Žemės gatvės")  # 2 words: a garble
        assert s.secondary_problems == []
        agent._prefill_slots_from_text("O dar sąskaitos klausimas turiu")
        assert s.secondary_problems and s.secondary_problems[0]["tipas"] == "billing"


class TestLiveCall0821Fixes:
    """Two live calls 2026-08-21: step hint/RAG overrode recap+findings (1),
    the bridge was a one-liner and 'kaip tai padaryti?' got 'ne mano
    sritis' (2), no problem stated -> an address hunt (3)."""

    def test_directive_turn_drops_step_hint_and_playbook(self, db_connection):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_power"}
        plain = agent._state_facts_block() or ""
        assert "THIS STEP" in plain
        agent._findings_directive = {
            "faktai": "x",
            "isvada": "y",
            "sprendimai": "",
            "pasiulymas": "",
        }
        isolated = agent._state_facts_block() or ""
        assert "IŠVADOS MOMENTAS" in isolated
        assert "THIS STEP" not in isolated and "PLAYBOOK" not in isolated

    def test_bridge_solution_syncs_the_walker_to_the_cable_step(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.evidence_drive import evidence_drive

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "bridge")
        monkeypatch.setattr(ev, "solution_step", lambda e, v: "dr_pick_cable")
        gotos = []
        r = {"verdict": "no_mac_observed", "step": "dr_offer_bridge"}
        engine = SimpleNamespace(
            state=SimpleNamespace(resolution=r, evidence={}, turn_count=3),
            _findings_announced=True,
            _evidence_last_ask_key=None,
            _evidence_asks={},
            _goto_step=lambda rr, t: (gotos.append(t), rr.__setitem__("step", t)),
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        assert evidence_drive(engine, "turiu kompiuterį") is None
        assert gotos == ["dr_pick_cable"] and r["solution_synced"] == "dr_pick_cable"

    def test_howto_at_standing_instruction_is_on_task(self):
        from types import SimpleNamespace

        from agent.perception_flow import classify_side_topic, is_howto

        assert is_howto("O kaip tai padaryti?") and is_howto("Padėkit, nežinau kaip")
        engine = SimpleNamespace(
            state=SimpleNamespace(
                customer_id="C1",
                case_closed=False,
                resolution={"verdict": "no_mac_observed", "step": "dr_pick_cable", "asked": True},
            ),
            _ticket_stage=None,
            _evidence_conflict=None,
            _end_confirm_pending=False,
            _resume_hold=False,
            _side_topic_this_turn=False,
            _side_topic_turns=0,
            _evidence_last_ask_key=None,
            _last_understanding={"tipas": "klausimas", "faktai": {}},
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
        )
        assert classify_side_topic(engine, "O kaip tai padaryti?") is False

    def test_problem_gate_scripted_then_directive_then_close(self, db_connection, monkeypatch):
        from agent.react_agent import ReactAgent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = ReactAgent(caller_phone="unknown")
        assert "problema" in agent._identification_scripted_reply("Atsikai daro")
        assert "problema" in agent._identification_scripted_reply("Vaikai neklauso")
        assert agent._identification_scripted_reply("Viki kur neklauso") is None
        assert agent._ident_directive["kind"] == "problem_gate"
        assert "PROBLEMOS VARTAI" in agent._state_facts_block()
        assert agent._identification_scripted_reply("Kokiu problemu?") is None
        assert agent._ident_directive["kind"] == "problem_gate"
        bye = agent._identification_scripted_reply("Mendulija")
        assert bye and "skambinkite" in bye and agent.state.case_closed


class TestLiveCall0824Fixes:
    """Live 2026-08-24: (1) the dr_register_router hint ('ALREADY registered')
    leaked into every ticket-dialogue turn — the agent said 'užregistravau' three
    times before create_ticket ever ran; (2) a caller who reported the cable
    ALREADY in the computer while still on dr_pick_cable got the plug instruction
    dictated to them anyway."""

    def _ticket_agent(self, db_connection=None):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060012353")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_register_router"}
        return agent

    def test_ticket_directive_suppresses_step_hint(self, db_connection):
        agent = self._ticket_agent()
        agent._bridge_bound = True
        agent._ticket_directive = {"kind": "phone_intro", "fallback": "Ar tiks numeris?"}
        block = agent._state_facts_block() or ""
        assert "TIKETO ŽINGSNIS" in block
        assert "THIS STEP" not in block and "PLAYBOOK" not in block
        # The tense rule rides along: registration has NOT happened yet.
        assert "užregistruosiu" in block and "niekada „užregistravau“" in block

    def test_ident_directive_suppresses_step_hint(self, db_connection):
        agent = self._ticket_agent()
        agent._ident_directive = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        block = agent._state_facts_block() or ""
        assert "THIS STEP" not in block and "PLAYBOOK" not in block

    def test_plug_report_skips_the_dead_instruct_step(self, db_connection, monkeypatch):
        from agent.resolution import get_strategy

        agent = self._ticket_agent()
        r = {"verdict": "no_mac_observed", "step": "dr_pick_cable", "asked": True}
        agent.state.resolution = r
        strat = get_strategy("no_mac_observed")
        reached = []
        monkeypatch.setattr(agent, "_simulate_bridge_connection", lambda: reached.append("sim"))
        monkeypatch.setattr(agent, "_advance_see_device", lambda rr: reached.append("see"))
        agent._advance_instruct(
            r, strat.step("dr_pick_cable"), strat, "kabelį jau įkišau į kompiuterį"
        )
        assert r["step"] == "dr_see_device" and reached == ["sim", "see"]

    def test_plain_done_still_advances_one_step(self, db_connection):
        from agent.resolution import get_strategy

        agent = self._ticket_agent()
        r = {"verdict": "no_mac_observed", "step": "dr_pick_cable", "asked": True}
        agent.state.resolution = r
        strat = get_strategy("no_mac_observed")
        agent._advance_instruct(r, strat.step("dr_pick_cable"), strat, "jau turiu rankoje")
        assert r["step"] == "dr_plug_pc"
