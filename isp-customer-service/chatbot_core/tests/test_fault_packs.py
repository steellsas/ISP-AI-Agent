"""
Fault packs (R5) — one file per fault + reusable modules + meta/tags.

Packs build their procedure through module calls; the knowledge schema tests
(test_knowledge_schema.py) guard the structure.
"""

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


class TestSolverMechanics:
    """R4b mechanics — evidence-led packs + the procedure solution kind."""

    def test_every_pack_with_evidence_is_evidence_led(self):
        # One driver (D-03): every internet pack declares evidence; the unclear
        # fault is its procedure alone.
        from agent.faults import evidence_led, pack_verdicts

        for verdict in pack_verdicts() - {"unclear_fault"}:
            assert evidence_led(verdict), verdict
        assert not evidence_led("unclear_fault")

    def test_line_fault_packs_start_their_procedure_from_telemetry(self):
        from agent.evidence import hypothesis_status, solution_for, solution_step, spec_for

        for verdict, first in (("link_down_local", "ll_ability"), ("crc_errors", "crc_ability")):
            assert hypothesis_status({}, spec_for(verdict)) == "confirmed"
            assert solution_for({}, verdict) == "procedure"
            assert solution_step({}, verdict) == first

    def test_walker_solution_syncs_step_and_hands_over(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "procedure")
        monkeypatch.setattr(ev, "solution_step", lambda e, v: "bind_mac")

        gotos = []
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(procedure={"verdict": "x", "step": "a"}),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=True,
                        pending_evidence_key=None,
                        evidence_ask_counts={},
                    ),
                    dialog=DialogState(turn_count=1),
                ),
                _goto_step=lambda r, t: gotos.append(t),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        assert evidence_drive(engine.state, engine.runtime, "taip") is None  # walker takes the turn
        assert gotos == ["bind_mac"]


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

    def test_anamnesis_seeds_ledger_on_activation(self, monkeypatch):
        from types import SimpleNamespace

        from agent.execute.diagnosis import _seed_evidence_from_anamnesis

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
        _seed_evidence_from_anamnesis(engine.state, engine.runtime)
        assert engine.state.diagnosis.evidence.get("changed_device", {}).get("value") == "yes"

    def test_pack_glosses_replace_raw_keys(self):
        from agent.evidence import gloss_label, gloss_value

        assert gloss_label("changed_device") == "routerio keitimas"
        assert gloss_value("yes", "changed_device") == "keitė arba prijungė naują įrenginį"
        assert gloss_label("lights") == "routerio lemputės"  # built-ins keep working


class TestNarratorWordedQuestions:
    """Persona (R5c): the first ask becomes a narrator GOAL directive; retries
    and formuluote:skriptas stay scripted; off-switch reverts everything."""

    def _engine(self):
        from types import SimpleNamespace

        return as_call(
            None,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(
                        procedure={"verdict": "no_mac_observed", "step": "dr_intro"}
                    ),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=True,
                        facts_recap_state="done",
                        pending_evidence_key=None,
                        evidence_ask_counts={},
                        pending_announcement="",
                    ),
                    dialog=DialogState(turn_count=1),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )

    def test_first_ask_delegates_to_narrator(self, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        engine = self._engine()
        assert evidence_drive(engine.state, engine.runtime, "labas") is None
        d = engine.state.turn.directives.evidence
        assert d and d["key"] == "recent_events" and d["reikia"]  # contextual anamnesis first
        assert (
            engine.state.diagnosis.evidence_ask_counts["recent_events"] == 1
        )  # ask bookkeeping intact

    def test_off_switch_keeps_scripted_wording(self, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        engine = self._engine()
        reply = evidence_drive(engine.state, engine.runtime, "labas")
        assert reply and "dingusi elektra" in reply  # ivykiai (kontekstinė anamnezė)
        assert engine.state.turn.directives.evidence is None

    def test_directive_lands_in_facts_block(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.evidence = {
            "key": "lights",
            "reikia": "ar dega bent viena lemputė",
            "kodel": "matysime ar gauna srovę",
            "klausimas": "Ar dega lemputė?",
        }
        block = context_card(agent.state, agent.runtime)
        assert block and "ASK NOW" in block and "ar dega bent viena lemputė" in block


class TestNarratorFindings:
    """Persona (2026-08-13, dead-router live call): the findings announce was a
    template dump ('routeris surastas: rado; lemputės: nedega...') — words FOR
    the agent, not speech. In narrator mode the findings become a GOAL
    directive; the off-switch keeps the scripted announce."""

    def _engine(self, monkeypatch):
        from types import SimpleNamespace

        return as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(
                        procedure={"verdict": "no_mac_observed", "step": "dr_intro"}
                    ),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=False,
                        facts_recap_state="done",
                        pending_evidence_key=None,
                        evidence_ask_counts={},
                        pending_announcement="",
                    ),
                    dialog=DialogState(turn_count=3),
                ),
                _ticket_need=lambda: "",
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )

    def _mock_confirmed(self, monkeypatch):
        from agent import evidence as ev

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        monkeypatch.setattr(ev, "fault_conclusion", lambda v: "routeris sugedęs")
        monkeypatch.setattr(
            ev, "solution_descriptions", lambda v: ["paleisti per kompiuterį", "meistras"]
        )
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "bridge")

    def test_no_opening_anamnesis_ladder(self, db_connection, monkeypatch):
        """DIALOGO_ETALONAS #2 (2026-09-03): the E follow-up ladder went away
        with the opening question — after the problem the flow goes straight
        to the address; targeted anamnesis lives in the packs."""
        from agent.decide.rules.reply import scripted_words

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = make_agent("unknown")
        s = agent.state
        s.intake.problem_type = "internet_down"
        reply = scripted_words(agent.state, agent.runtime, "Nežinau, nepastebėjau.")
        assert reply and "adres" in reply.lower()
        assert "paskutinį kartą" not in (reply or "")

    def test_wait_signal_holds_instead_of_reasking(self, monkeypatch):
        """C (2026-08-20): 'palaukit, ateinu' -> Gerai, lauksiu; no retry burn."""
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: None)
        monkeypatch.setattr(
            ev,
            "next_missing",
            lambda e, s, c: ("device_present", {"klausimas": "Radote routerį?"}),
        )
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(
                        procedure={"verdict": "no_mac_observed", "step": "dr_intro"}
                    ),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=False,
                        facts_recap_state="done",
                        pending_evidence_key="device_present",
                        evidence_ask_counts={"device_present": 1},
                        pending_announcement="",
                    ),
                    dialog=DialogState(turn_count=2),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        reply = evidence_drive(engine.state, engine.runtime, "Palaukit, tuoj ateinu.")
        assert reply and "lauksiu" in reply.lower()
        assert engine.state.diagnosis.evidence_ask_counts["device_present"] == 1  # retry NOT burned

    def test_reask_phrase_has_no_internal_labels(self):
        from agent.contract.locale import phrase

        text = phrase("identification.reask_reason", topic="routeris surastas", question="Radote?")
        assert "routeris surastas" not in text and "Radote?" in text

    def test_phone_echo_is_consent(self, monkeypatch):
        """D (2026-08-20): the caller echoing our own phone offer is a yes."""
        from agent.barge_in import token_overlap

        q = "Ar tiks numeris, iš kurio skambinate? — ar tiks tas, iš kurio skambinate?"
        assert token_overlap("Ar tiks tas, iš kurio skambinu?", q) >= 0.8
        assert token_overlap("O kiek kainuoja meistras?", q) < 0.8

    def test_recap_delegates_to_narrator(self, monkeypatch):
        from agent.decide.rules.evidence import maybe_facts_recap

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        from types import SimpleNamespace

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    diagnosis=DiagnosisState(
                        evidence={"lights": {"value": "off", "source": "client"}},
                        facts_recap_state="",
                    )
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        from agent import evidence as ev

        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        assert maybe_facts_recap(engine.state, engine.runtime) is None
        assert (
            engine.state.turn.directives.recap
            and "nedega" in engine.state.turn.directives.recap["faktai"]
        )
        assert engine.state.diagnosis.facts_recap_state == "pending"

    def test_recap_off_switch_stays_scripted(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.decide.rules.evidence import maybe_facts_recap

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        monkeypatch.setattr(ev, "client_facts_lt", lambda e: "routerio lemputės: nedega")
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    diagnosis=DiagnosisState(evidence={"x": {}}, facts_recap_state="")
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        reply = maybe_facts_recap(engine.state, engine.runtime)
        assert reply and "Pasitikslinu" in reply and engine.state.turn.directives.recap is None

    def test_recap_directive_lands_in_facts_block(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.recap = {"faktai": "routerio lemputės: nedega"}
        block = context_card(agent.state, agent.runtime)
        assert "CHECK BACK" in block and "nedega" in block

    def test_findings_delegate_to_narrator(self, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        self._mock_confirmed(monkeypatch)
        engine = self._engine(monkeypatch)
        assert (
            evidence_drive(engine.state, engine.runtime, "nedega") is None
        )  # narrator takes the turn
        d = engine.state.turn.directives.findings
        assert d and d["isvada"] == "routeris sugedęs"
        assert "ARBA" in d["solutions"]
        assert engine.state.diagnosis.findings_announced is True  # said once, never re-dumped

    def test_off_switch_keeps_scripted_announce(self, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        self._mock_confirmed(monkeypatch)
        engine = self._engine(monkeypatch)
        assert (
            evidence_drive(engine.state, engine.runtime, "nedega") is None
        )  # bridge -> solver drives
        assert engine.state.turn.directives.findings is None
        assert "Ką patikrinome" in engine.state.diagnosis.pending_announcement

    def test_findings_directive_lands_in_facts_block(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.findings = {
            "faktai": "routerio lemputės: nedega",
            "isvada": "routeris sugedęs",
            "solutions": "paleisti per kompiuterį ARBA meistras",
        }
        block = context_card(agent.state, agent.runtime)
        assert block and "FINDINGS MOMENT" in block and "routeris sugedęs" in block
        assert "Offer the choice" in block

    def test_bridge_anchor_lands_in_narrator_facts(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.resolution.bridge_plug_reported = True
        block = context_card(agent.state, agent.runtime)
        assert block and "BRIDGE PHASE" in block and "do NOT ask about the router" in block


class TestTicketFirst:
    """2026-08-13 live call: the dead router NEEDS a registration — the bridge
    is a convenience. Solver 'close' may not skip the ticket; a demand is
    never a side topic; the goodbye hears the demand too."""

    def test_garbled_demands_are_demands(self):
        from agent.perceive.detectors import detect_refuse_or_ticket

        assert detect_refuse_or_ticket("Išregistruoti meistrą ir paleisti internetą") == "demand"
        assert detect_refuse_or_ticket("Dar prašau, žegistruokit gedimą") == "demand"
        assert detect_refuse_or_ticket("Neregistruokite, bandome toliau") != "demand"

    def test_infinitive_needs_intent(self):
        """Live 2026-08-14: small talk with the bare infinitive escalated
        mid-collection and the findings moment never happened."""
        from agent.perceive.detectors import detect_refuse_or_ticket

        assert (
            detect_refuse_or_ticket(
                "O jums dažnai taip skamina gedimus? Registruoti. Gerai, padariau tai."
            )
            is None
        )
        assert detect_refuse_or_ticket("Noriu registruoti gedimą") == "demand"
        assert detect_refuse_or_ticket("Gal galite užregistruoti meistrą?") == "demand"

    def test_demand_is_never_a_side_topic(self, monkeypatch):
        from types import SimpleNamespace

        from agent.perceive.side_topic import classify_side_topic

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    identity=IdentityState(customer_id="C1"),
                    closing=ClosingState(case_closed=False),
                    diagnosis=DiagnosisState(),
                    turn=TurnScratch(
                        side_topic_active=False, understanding={"type": "deviation", "facts": {}}
                    ),
                    dialog=DialogState(
                        side_topic_streak=0, end_confirm_pending=False, resume_hold_due=False
                    ),
                    ticket=TicketState(stage=None),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        assert (
            classify_side_topic(
                engine.state, engine.runtime, "Išregistruoti meistrą ir paleisti internetą"
            )
            is False
        )
        assert engine.state.turn.side_topic_active is False

    def test_solver_close_after_bridge_registers(self, monkeypatch):
        from types import SimpleNamespace

        from agent.decide.rules.diagnosis import close_or_register

        calls = []
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(
                        procedure={"verdict": "no_mac_observed", "telemetry_fixed": True},
                        bridge_bound=True,
                    ),
                    ticket=TicketState(ticket_id=None),
                    closing=ClosingState(case_closed=False, closed_reason=None),
                ),
                _drive_escalate=lambda d: calls.append("escalate") or "Užregistruosiu gedimą…",
                _settle_hypothesis=lambda *a, **k: None,
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        reply = close_or_register(engine.state, engine.runtime, "Puiku!")
        assert calls == ["escalate"] and "gedim" in reply
        assert engine.state.closing.case_closed is False  # the dialogue closes it later

    def test_solver_close_without_bridge_stays_a_close(self, monkeypatch):
        from types import SimpleNamespace

        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(procedure={"verdict": "x"}, bridge_bound=False),
                    ticket=TicketState(ticket_id=None),
                    closing=ClosingState(case_closed=False, closed_reason=None),
                ),
                _settle_hypothesis=lambda *a, **k: None,
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        from agent.decide.rules.diagnosis import close_or_register

        assert "Puiku" in close_or_register(engine.state, engine.runtime, "")
        assert engine.state.closing.case_closed is True

    def test_pack_declares_ticket_first_offer(self):
        from agent.evidence import fault_offer_goal

        text = fault_offer_goal("no_mac_observed")
        assert text and "technician" in text and "computer" in text

    def test_open_goals_follow_the_ledger(self):
        from agent.evidence import CLIENT, open_goals_lt

        assert "found the router" in open_goals_lt({}, "no_mac_observed")
        ev = {
            "device_present": {"value": "found", "source": CLIENT, "turn": 1},
            "lights": {"value": "off", "source": CLIENT, "turn": 2},
        }
        goals = open_goals_lt(ev, "no_mac_observed")
        assert "power lead" in goals and "found the router" not in goals
        # when-gated keys stay hidden until eligible; engine-only gates never show
        assert "computer" not in goals and "LAN" not in goals

    def test_situational_block_lands_in_narrator_facts(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST001"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        block = context_card(agent.state, agent.runtime)
        assert block and "STILL TO FIND OUT" in block and "bring the conversation back" in block

    def test_findings_prefer_the_pack_offer(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.turn.directives.findings = {
            "faktai": "routerio lemputės: nedega",
            "isvada": "routeris sugedęs",
            "solutions": "a ARBA b",
            "offer": "Pasakyk, kad užregistruosi meistrą; pasiūlyk tiltą.",
        }
        block = context_card(agent.state, agent.runtime)
        assert "užregistruosi meistrą" in block
        assert "Pasiūlyk pasirinkimą" not in block


class TestStepAwareness:
    """VOICE_PLAN 1 žingsnis (L1+L2): one question per turn, the step's goal
    (`tikslas`) drives evaluative reactions, repeats come with an explanation,
    and the solver reads the walked path from the journal."""

    def test_caller_question_is_single(self):
        from agent.contract.locale import phrase

        q = phrase("identification.questions.caller")
        assert q.count("?") == 1 and "sudar" not in q

    def test_goal_flows_through_build(self):
        from agent.faults import build_strategy

        strat = build_strategy("no_mac_observed")
        by_id = {st.id: st for st in strat.steps}
        assert "agrees" in by_id["dr_intro"].goal
        assert "light" in by_id["dr_lights"].goal
        # module instance override (as: dr_verify) carries its own goal
        assert "connected computer" in by_id["dr_verify"].goal

    def test_goto_step_writes_the_journal(self):
        from types import SimpleNamespace

        from agent.decide.procedure import goto_step

        state = GraphState()
        rt = SimpleNamespace(tracer=SimpleNamespace(emit=lambda *a, **k: None))
        r = {"step": "dr_intro"}
        goto_step(state, rt, r, "dr_lights")
        goto_step(state, rt, r, "dr_lights")  # same step -> no duplicate entry
        goto_step(state, rt, r, "dr_power")
        assert r["journal"] == ["dr_intro→dr_lights", "dr_lights→dr_power"]

    def test_facts_block_states_goal_and_repeat(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST001"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 2},
        }
        block = context_card(agent.state, agent.runtime)
        assert "STEP GOAL" in block and "lemput" in block
        assert "STEP REPEATED" in block

    def test_first_presentation_has_no_repeat_directive(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST001"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 1},
        }
        block = context_card(agent.state, agent.runtime)
        assert "STEP REPEATED" not in block

    def test_solver_context_includes_the_journey(self, db_connection):
        from agent.decide.rules.diagnosis import build_solver_context

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST001"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_power",
            "journal": ["dr_intro→dr_lights", "dr_lights→dr_power"],
        }
        ctx = build_solver_context(agent.state, agent.runtime, "nedega")
        assert "STEPS WALKED" in ctx and "dr_intro→dr_lights" in ctx


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
        # facts pick the SOLUTION (solutions), not the hypothesis
        assert spec["confirmed_when"] == []
        # perception vocabulary: canonical values are declared per fact
        assert set(spec["client"]["changed_device"]["answers"]) == {"yes", "no"}

    def test_healthy_to_router_conditional_asking(self):
        from agent.evidence import spec_for

        spec = spec_for("healthy_to_router")
        assert spec["client"]["connection_type"]["when"] == ["fail_device=computer"]
        assert spec["client"]["rebooted"]["when"] == ["fail_scope=all"]

    def test_goal_present_for_narrator_directives(self):
        """`goal` is the narrator directive — every declared fact must state
        its GOAL, not only the wording."""
        from agent.evidence import spec_for

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            for key, item in spec_for(verdict)["client"].items():
                assert item.get("goal"), f"{verdict}.{key} has no goal"


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
        summary = agent._build_call_summary()
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

    def test_pack_carries_the_contextual_anamnesis(self, db_connection):
        from agent.evidence import spec_for

        spec = spec_for("no_mac_observed")
        item = (spec.get("client") or {}).get("recent_events")
        from agent.contract.locale import phrase

        assert item and "elektra" in phrase(item["question_key"])
        assert "linijoje nesimato" in phrase(item["why_key"])  # telemetrijos kontekstas


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
        from agent.perceive.slots import prefill_slots_from_text

        from tests.calls import make_agent

        agent = make_agent("unknown")
        s = agent.state
        prefill_slots_from_text(agent.state, agent.runtime, "Neveikia internetas")
        assert s.intake.problem_type == "internet_down"
        s.identity.customer_id = "CUST009"
        s.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_intro"}
        prefill_slots_from_text(agent.state, agent.runtime, "O dar televizorius man blogai rodo")
        assert s.intake.problem_type == "internet_down"  # frozen
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"
        # dedupe: the same type mentioned again does not duplicate
        prefill_slots_from_text(agent.state, agent.runtime, "Tas televizorius vis dar blogai")
        assert len(s.intake.secondary_problems) == 1
        # Competence policy (2026-09-02): a not_ours type (billing) never
        # becomes a secondary TECH problem — it is not ours to put on a ticket.
        prefill_slots_from_text(agent.state, agent.runtime, "O dar sąskaitos klausimas turiu")
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


class TestWalkerFollowsLedger:
    """B2 (Andrius 2026-08-21): one source of truth — in solver-driven packs the
    walker reads no answers until the evidence layer hands over; facts may
    carry a `zingsnis` pointer so RAG/hint/tikslas follow the ledger."""

    def test_walker_silent_during_evidence_collection(self, monkeypatch):
        from types import SimpleNamespace

        from agent.decide.procedure import owns_answer
        from agent.resolution import get_strategy

        strat = get_strategy("no_mac_observed")
        engine = as_call(
            monkeypatch,
            SimpleNamespace(state=GraphState(resolution=ResolutionState(bridge_bound=False))),
        )
        r = {"verdict": "no_mac_observed", "step": "dr_lights"}
        assert owns_answer(engine.state, engine.runtime, r, strat.step("dr_lights")) is False
        assert owns_answer(engine.state, engine.runtime, r, strat.step("escalate")) is True
        assert owns_answer(engine.state, engine.runtime, r, strat.step("dr_see_device")) is True
        r["solution_synced"] = "dr_plug_pc"
        assert owns_answer(engine.state, engine.runtime, r, strat.step("dr_plug_pc")) is True
        engine.state.resolution.bridge_bound = True
        del r["solution_synced"]
        assert owns_answer(engine.state, engine.runtime, r, strat.step("dr_verify")) is True

    def test_fact_pointer_moves_the_walker(self, monkeypatch):
        from types import SimpleNamespace

        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        gotos = []
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(
                        procedure={"verdict": "no_mac_observed", "step": "dr_intro"}
                    ),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=True,
                        facts_recap_state="done",
                        pending_evidence_key=None,
                        evidence_ask_counts={},
                        pending_announcement="",
                    ),
                    dialog=DialogState(turn_count=1),
                ),
                _goto_step=lambda r, t: (gotos.append(t), r.__setitem__("step", t)),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        reply = evidence_drive(engine.state, engine.runtime, "labas")
        assert reply and "elektra" in reply  # first fact asked (ivykiai, 2026-09-03)
        assert gotos == ["dr_lights"]  # pointer followed the fact


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
        from agent.perceive.slots import prefill_slots_from_text

        from tests.calls import make_agent

        agent = make_agent("unknown")
        s = agent.state
        s.intake.problem_type = "internet_down"
        s.identity.customer_id = "CUST009"
        s.resolution.procedure = {"verdict": "no_mac_observed", "step": "escalate"}
        agent.state.ticket.stage = "hours"
        prefill_slots_from_text(agent.state, agent.runtime, "Sąskaitos žemės gatvės klausimas")
        assert s.intake.secondary_problems == []
        agent.state.ticket.stage = None
        prefill_slots_from_text(agent.state, agent.runtime, "Žemės gatvės")  # 2 words: a garble
        assert s.intake.secondary_problems == []
        prefill_slots_from_text(agent.state, agent.runtime, "O dar televizorius man blogai rodo")
        assert s.intake.secondary_problems and s.intake.secondary_problems[0]["type"] == "tv"


class TestLiveCall0821Fixes:
    """Two live calls 2026-08-21: step hint/RAG overrode recap+findings (1),
    the bridge was a one-liner and 'kaip tai padaryti?' got 'ne mano
    sritis' (2), no problem stated -> an address hunt (3)."""

    def test_directive_turn_drops_step_hint_and_playbook(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {"verdict": "no_mac_observed", "step": "dr_power"}
        plain = context_card(agent.state, agent.runtime) or ""
        assert "THIS STEP" in plain
        agent.state.turn.directives.findings = {
            "faktai": "x",
            "isvada": "y",
            "solutions": "",
            "offer": "",
        }
        isolated = context_card(agent.state, agent.runtime) or ""
        assert "FINDINGS MOMENT" in isolated
        assert "THIS STEP" not in isolated and "PLAYBOOK" not in isolated

    def test_bridge_solution_syncs_the_walker_to_the_cable_step(self, monkeypatch):
        from types import SimpleNamespace

        from agent import evidence as ev
        from agent.decide.rules.evidence import evidence_drive

        monkeypatch.setattr(ev, "spec_for", lambda v: {"client": {}})
        monkeypatch.setattr(ev, "hypothesis_status", lambda e, s: "confirmed")
        monkeypatch.setattr(ev, "solution_for", lambda e, v: "bridge")
        monkeypatch.setattr(ev, "solution_step", lambda e, v: "dr_pick_cable")
        gotos = []
        r = {"verdict": "no_mac_observed", "step": "dr_offer_bridge"}
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    resolution=ResolutionState(procedure=r),
                    diagnosis=DiagnosisState(
                        evidence={},
                        findings_announced=True,
                        pending_evidence_key=None,
                        evidence_ask_counts={},
                    ),
                    dialog=DialogState(turn_count=3),
                ),
                _goto_step=lambda rr, t: (gotos.append(t), rr.__setitem__("step", t)),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        assert evidence_drive(engine.state, engine.runtime, "turiu kompiuterį") is None
        procedure = engine.state.resolution.procedure  # the state holds its own copy of r
        assert gotos == ["dr_pick_cable"] and procedure["solution_synced"] == "dr_pick_cable"

    def test_howto_at_standing_instruction_is_on_task(self, monkeypatch):
        from types import SimpleNamespace

        from agent.perceive.side_topic import classify_side_topic, is_howto

        assert is_howto("O kaip tai padaryti?") and is_howto("Padėkit, nežinau kaip")
        engine = as_call(
            monkeypatch,
            SimpleNamespace(
                state=GraphState(
                    identity=IdentityState(customer_id="C1"),
                    closing=ClosingState(case_closed=False),
                    resolution=ResolutionState(
                        procedure={
                            "verdict": "no_mac_observed",
                            "step": "dr_pick_cable",
                            "asked": True,
                        }
                    ),
                    diagnosis=DiagnosisState(pending_evidence_key=None),
                    turn=TurnScratch(
                        side_topic_active=False, understanding={"type": "question", "facts": {}}
                    ),
                    dialog=DialogState(
                        side_topic_streak=0, end_confirm_pending=False, resume_hold_due=False
                    ),
                    ticket=TicketState(stage=None),
                ),
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
            ),
        )
        assert classify_side_topic(engine.state, engine.runtime, "O kaip tai padaryti?") is False

    def test_problem_gate_scripted_then_directive_then_close(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        monkeypatch.setenv("NARRATOR_QUESTIONS", "on")
        agent = make_agent("unknown")
        assert "problema" in scripted_words(agent.state, agent.runtime, "Atsikai daro")
        assert "problema" in scripted_words(agent.state, agent.runtime, "Vaikai neklauso")
        assert scripted_words(agent.state, agent.runtime, "Viki kur neklauso") is None
        assert agent.state.turn.directives.ident["kind"] == "problem_gate"
        assert "PROBLEM GATE" in context_card(agent.state, agent.runtime)
        assert scripted_words(agent.state, agent.runtime, "Kokiu problemu?") is None
        assert agent.state.turn.directives.ident["kind"] == "problem_gate"
        bye = scripted_words(agent.state, agent.runtime, "Mendulija")
        assert bye and "skambinkite" in bye and agent.state.closing.case_closed


class TestLiveCall0824Fixes:
    """Live 2026-08-24: (1) the dr_register_router hint ('ALREADY registered')
    leaked into every ticket-dialogue turn — the agent said 'užregistravau' three
    times before create_ticket ever ran; (2) a caller who reported the cable
    ALREADY in the computer while still on dr_pick_cable got the plug instruction
    dictated to them anyway."""

    def _ticket_agent(self, db_connection=None):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_register_router",
        }
        return agent

    def test_ticket_directive_suppresses_step_hint(self, db_connection):
        from agent.speak.context_card import context_card

        agent = self._ticket_agent()
        agent.state.resolution.bridge_bound = True
        agent.state.turn.directives.ticket = {"kind": "phone_intro", "fallback": "Ar tiks numeris?"}
        block = context_card(agent.state, agent.runtime) or ""
        assert "TICKET STEP" in block
        assert "THIS STEP" not in block and "PLAYBOOK" not in block
        # The tense rule rides along: registration has NOT happened yet.
        assert "užregistruosiu" in block and "never „užregistravau“" in block

    def test_ident_directive_suppresses_step_hint(self, db_connection):
        from agent.speak.context_card import context_card

        agent = self._ticket_agent()
        agent.state.turn.directives.ident = {"kind": "anamnesis", "adresas": None, "fallback": "x"}
        block = context_card(agent.state, agent.runtime) or ""
        assert "THIS STEP" not in block and "PLAYBOOK" not in block

    def test_plug_report_skips_the_dead_instruct_step(self, db_connection, monkeypatch):
        from agent.decide.procedure import advance_instruct
        from agent.resolution import get_strategy

        agent = self._ticket_agent()
        r = {"verdict": "no_mac_observed", "step": "dr_pick_cable", "asked": True}
        agent.state.resolution.procedure = r
        strat = get_strategy("no_mac_observed")
        reached = []
        monkeypatch.setattr(
            "agent.executor_flow.simulate_bridge_connection",
            lambda state, rt: reached.append("sim"),
        )
        monkeypatch.setattr(
            "agent.decide.procedure.advance_see_device", lambda state, rt, rr: reached.append("see")
        )
        advance_instruct(
            agent.state,
            agent.runtime,
            r,
            strat.step("dr_pick_cable"),
            strat,
            "kabelį jau įkišau į kompiuterį",
        )
        assert r["step"] == "dr_see_device" and reached == ["sim", "see"]

    def test_plain_done_still_advances_one_step(self, db_connection):
        from agent.decide.procedure import advance_instruct
        from agent.resolution import get_strategy

        agent = self._ticket_agent()
        r = {"verdict": "no_mac_observed", "step": "dr_pick_cable", "asked": True}
        agent.state.resolution.procedure = r
        strat = get_strategy("no_mac_observed")
        advance_instruct(
            agent.state, agent.runtime, r, strat.step("dr_pick_cable"), strat, "jau turiu rankoje"
        )
        assert r["step"] == "dr_plug_pc"


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
