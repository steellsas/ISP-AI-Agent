"""Ledger v1 (Phase 4.5) — evidence ledger: two sources, conflicts, extraction.

Run: pytest tests/test_evidence.py -v
"""

import json
from unittest.mock import patch


class TestSetFact:
    def test_telemetry_overwrites_with_history(self):
        from agent.evidence import TELEMETRY, set_fact

        ev = {}
        set_fact(ev, "verdict", "no_mac_observed", TELEMETRY, 1)
        set_fact(ev, "verdict", "foreign_mac", TELEMETRY, 5)  # re-diagnose after plug-in
        assert ev["verdict"]["value"] == "foreign_mac"
        assert [h["value"] for h in ev["verdict"]["history"]] == [
            "no_mac_observed",
            "foreign_mac",
        ]
        assert ev["verdict"]["conflict"] is False

    def test_client_words_never_overwrite_telemetry(self):
        from agent.evidence import CLIENT, TELEMETRY, set_fact

        ev = {}
        set_fact(ev, "verdict", "no_mac_observed", TELEMETRY, 1)
        set_fact(ev, "verdict", "veikia", CLIENT, 2)  # "man viskas veikia"
        assert ev["verdict"]["value"] == "no_mac_observed"
        assert ev["verdict"]["source"] == TELEMETRY

    def test_contradicting_client_value_flags_conflict(self):
        from agent.evidence import CLIENT, set_fact

        ev = {}
        set_fact(ev, "has_computer", "no", CLIENT, 3)
        entry = set_fact(ev, "has_computer", "yes", CLIENT, 6)
        assert entry["conflict"] is True
        assert entry["value"] == "no" and entry["pending"] == "yes"

    def test_next_answer_settles_the_conflict(self):
        from agent.evidence import CLIENT, set_fact

        ev = {}
        set_fact(ev, "has_computer", "no", CLIENT, 3)
        set_fact(ev, "has_computer", "yes", CLIENT, 6)
        entry = set_fact(ev, "has_computer", "yes", CLIENT, 7)  # the clarify answer
        assert entry["conflict"] is False
        assert entry["value"] == "yes" and entry.get("resolved") is True

    def test_same_value_repeat_is_not_a_conflict(self):
        from agent.evidence import CLIENT, set_fact

        ev = {}
        set_fact(ev, "lights", "off", CLIENT, 2)
        entry = set_fact(ev, "lights", "off", CLIENT, 4)
        assert entry["conflict"] is False and entry["turn"] == 4


class TestExtraction:
    def test_core_no_mac_facts(self):
        from agent.evidence import extract_client_facts as x

        assert x("Neturi kompiutera, tik telefonas") == {"has_computer": "no"}
        assert x("Turiu kompiuterį namuose")["has_computer"] == "yes"
        assert x("Nedega nė viena lemputė")["lights"] == "off"
        assert x("Lemputės dega žaliai")["lights"] == "on"
        assert x("Lemputė mirksi raudonai")["lights"] == "blinking"
        assert x("Maitinimo laidas gerai įkištas į rozetę")["power_cable"] == "plugged"
        assert x("Kabelis buvo atjungtas nuo routerio")["power_cable"] == "unplugged"
        assert x("Pabandžiau kitą rozetę, nepadėjo")["outlet_works"] == "tried"
        assert x("Radau tą routerio dėžutę su antena")["device_present"] == "found"

    def test_negation_attaches_to_the_right_noun(self):
        # Eval S4 regression: "Neturiu KITO ROUTERIO, tik kompiuterį" was read
        # as has_computer=no and the solution flipped to ticket instead of
        # bridge. The negation must attach to the computer itself.
        from agent.evidence import extract_client_facts as x

        assert x("Neturiu kito routerio, tik kompiuterį")["has_computer"] == "yes"
        assert x("Turiu tik kompiuterį")["has_computer"] == "yes"
        assert x("Neturiu kompiuterio")["has_computer"] == "no"
        assert x("Nėra jokio kompiuterio namuose")["has_computer"] == "no"

    def test_lights_answer_implies_device_present(self):
        # Answering about the lights means the caller is AT the device — the
        # device_present question must not be re-asked (eval S4: it was, then
        # given up on while the caller stood at the router).
        from agent.evidence import extract_client_facts as x

        facts = x("Ne, nešviečia jokia lemputė")
        assert facts["lights"] == "off"
        assert facts["device_present"] == "found"

    def test_real_value_replaces_gave_up_marker_without_conflict(self):
        from agent.evidence import CLIENT, set_fact

        ev = {}
        set_fact(ev, "power_cable", "unknown", CLIENT, 5)  # give-up marker
        entry = set_fact(ev, "power_cable", "plugged", CLIENT, 7)
        assert entry["value"] == "plugged" and entry["conflict"] is False

    def test_conservative_on_garble_and_unrelated(self):
        from agent.evidence import extract_client_facts as x

        assert x("Kurs komentai") == {}
        assert x("Žybavo audro buvo dingus, elektra nebeveikė") == {}
        assert x("") == {}
        assert x(None) == {}


class _CaptureTracer:
    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


def _diagnosing_agent():
    from tests.calls import make_agent

    agent = make_agent("+37060012353", tracer=_CaptureTracer())
    agent.state.identity.customer_id = "CUST009"
    agent.state.intake.problem_type = "internet_down"
    agent.state.diagnosis.hypothesis = {
        "cause": "no_mac_observed",
        "status": "testing",
        "because": ["linijoje nematomas įrenginys"],
    }
    agent.state.resolution.procedure = {
        "verdict": "no_mac_observed",
        "step": "dr_lights",
        "asked": True,
    }
    return agent


class TestAgentWiring:
    def test_telemetry_verdict_lands_on_ledger(self):
        from agent.narrator_flow import update_state_from_observation

        agent = _diagnosing_agent()
        obs = json.dumps({"verdict": {"reason": "no_mac_observed", "side": "unclear"}})
        update_state_from_observation(agent.state, agent.runtime, "diagnose_connection", obs)
        assert agent.state.diagnosis.evidence["verdict"]["value"] == "no_mac_observed"
        assert agent.state.diagnosis.evidence["verdict"]["source"] == "telemetry"

    def test_ingest_fills_client_facts(self):
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(
            agent.state, agent.runtime, "Nedega nė viena lemputė, laidas įkištas"
        )
        assert agent.state.diagnosis.evidence["lights"]["value"] == "off"
        assert agent.state.diagnosis.evidence["power_cable"]["value"] == "plugged"

    def test_contradiction_asks_one_clarify_then_settles(self):
        from agent.contract.locale import phrase
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import ingest_client_evidence
        from agent.solver_flow import solver_drive_turn
        from agent.walker_flow import advance_resolution

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio, tik telefonas")
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį, galim bandyti")
        assert agent.state.diagnosis.evidence_conflict is not None
        # The solver yields, the walker holds, the scripted clarify goes out.
        assert (
            solver_drive_turn(agent.state, agent.runtime, "Turiu kompiuterį, galim bandyti") is None
        )
        advance_resolution(agent.state, agent.runtime, "Turiu kompiuterį, galim bandyti")
        assert agent.state.resolution.procedure["step"] == "dr_lights"  # held, not advanced
        reply = identification_scripted_reply(
            agent.state, agent.runtime, "Turiu kompiuterį, galim bandyti"
        )
        assert reply == phrase(
            "identification.evidence_conflict",
            topic="ar turite kompiuterį",
            a="neturite",
            b="turite",
        )
        # The settling answer resolves the fact; no second clarify.
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį")
        e = agent.state.diagnosis.evidence["has_computer"]
        assert e["value"] == "yes" and e["conflict"] is False
        assert (
            agent.state.diagnosis.evidence_conflict is None
            and agent.state.diagnosis.evidence_conflict_asked_key is None
        )

    def test_bare_polarity_settles_yes_no_conflict(self):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio, tik telefonas")
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį vis dėlto")
        identification_scripted_reply(agent.state, agent.runtime, "x")  # asks the clarify
        ingest_client_evidence(agent.state, agent.runtime, "Taip.")  # bare yes
        assert agent.state.diagnosis.evidence["has_computer"]["value"] == "yes"

    def test_unreadable_settle_keeps_latest_and_stops_asking(self):
        from agent.identification_flow import identification_scripted_reply
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio, tik telefonas")
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį vis dėlto")
        identification_scripted_reply(agent.state, agent.runtime, "x")
        ingest_client_evidence(agent.state, agent.runtime, "Kurs komentai")  # garble
        e = agent.state.diagnosis.evidence["has_computer"]
        assert e["conflict"] is False and e["value"] == "yes"  # latest stated wins
        assert agent.state.diagnosis.evidence_conflict_asked_key is None

    def test_facts_block_and_solver_context_carry_ledger(self):
        from agent.narrator_flow import state_facts_block
        from agent.perception_flow import ingest_client_evidence
        from agent.solver_flow import build_solver_context

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        facts = state_facts_block(agent.state, agent.runtime)
        assert facts and "ĮRODYMŲ ŽURNALAS" in facts and "nedega" in facts
        ctx = build_solver_context(agent.state, agent.runtime, "tęsiam")
        assert "EVIDENCE LEDGER" in ctx

    def test_ticket_carries_client_evidence(self, db_connection):
        from agent.executor_flow import register_ticket_from_state
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        agent.state.ticket.contact_phone = "+37060012353"
        agent.state.ticket.contact_hours = "bet kada"
        register_ticket_from_state(agent.state, agent.runtime, None)
        assert agent.state.ticket.ticket_id
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket.ticket_id,)
            )
            details = dict(cur.fetchone())["details"]
        assert "Patikrinta su klientu" in details
        assert "routerio lemputės: nedega" in details
        assert "rozetė: bandyta" in details

    def test_spec_and_need_load_from_faults_yaml(self):
        from agent.evidence import fault_need, spec_for

        spec = spec_for("no_mac_observed")
        assert spec is not None
        assert list(spec["client"]) == [
            "recent_events",  # kontekstinė anamnezė (DIALOGO_ETALONAS #2, 2026-09-03)
            "device_present",
            "lights",
            "power_cable",
            "outlet_works",
            "has_computer",
            "lan_active",  # bridge-fail ladder only (kada: [tilto_fazeje])
        ]
        assert fault_need("no_mac_observed") == "reikalingas naujas maršrutizatorius"
        assert spec_for("nesamas_verdiktas") is None

    def test_evidence_drive_asks_in_order_with_kada_gates(self):
        from agent.evidence_drive import evidence_drive
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        # Nothing known -> the first question is the contextual anamnesis
        # (ivykiai, 2026-09-03), then device_present (lights stays gated).
        q0 = evidence_drive(agent.state, agent.runtime, "galim patikrinti")
        assert "elektra" in q0
        ingest_client_evidence(agent.state, agent.runtime, "Ne, nieko neįvyko, elektra nedingo")
        q1 = evidence_drive(agent.state, agent.runtime, "nieko")
        assert "Susiraskite routerį" in q1
        ingest_client_evidence(agent.state, agent.runtime, "Radau tą routerio dėžutę su antena")
        q2 = evidence_drive(agent.state, agent.runtime, "radau")
        assert "bent viena lemputė" in q2
        ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        q3 = evidence_drive(agent.state, agent.runtime, "nedega")
        assert "maitinimo laidas" in q3

    def test_unreadable_answers_escalate_wording_then_give_up(self):
        from agent.evidence_drive import evidence_drive

        agent = _diagnosing_agent()
        q1 = evidence_drive(agent.state, agent.runtime, "x")
        assert "elektra" in q1  # level 1 (ivykiai first, 2026-09-03)
        q2 = evidence_drive(agent.state, agent.runtime, "Kurs komentai")  # extractor got nothing
        assert "šviesa" in q2  # paprasciau (level 2)
        q3 = evidence_drive(agent.state, agent.runtime, "Vis tiek nesuprantu")
        # Gave up on ivykiai -> recorded "unknown"; the plan moves on to the
        # next fact (device_present) instead of stalling.
        assert agent.state.diagnosis.evidence["recent_events"]["value"] == "unknown"
        assert q3 is not None and "Susiraskite routerį" in q3

    def test_confirmed_with_no_computer_escalates_to_ticket(self):
        from agent.evidence_drive import evidence_drive
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        ingest_client_evidence(
            agent.state, agent.runtime, "Maitinimo laidas gerai įkištas į rozetę"
        )
        ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio, tik telefonas")
        # Round 3: the first confirmed moment READS THE FACTS BACK first.
        recap = evidence_drive(agent.state, agent.runtime, "neturiu")
        assert recap is not None and "Pasitikslinu" in recap
        reply = evidence_drive(agent.state, agent.runtime, "taip, teisingai")
        assert reply is not None and "Ar tiks numeris" in reply
        assert agent.state.ticket.stage == "phone"

    def test_confirmed_with_computer_yields_to_solver_bridge(self):
        from agent.evidence_drive import evidence_drive
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        ingest_client_evidence(
            agent.state, agent.runtime, "Maitinimo laidas gerai įkištas į rozetę"
        )
        ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį")
        recap = evidence_drive(
            agent.state, agent.runtime, "turiu"
        )  # round 3: recap checkpoint first
        assert recap is not None and "Pasitikslinu" in recap
        assert (
            evidence_drive(agent.state, agent.runtime, "taip") is None
        )  # then solver drives the bridge

    def test_confirmed_but_device_unknown_asks_has_computer(self):
        from agent.evidence_drive import evidence_drive
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė")
        ingest_client_evidence(
            agent.state, agent.runtime, "Maitinimo laidas gerai įkištas į rozetę"
        )
        ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        recap = evidence_drive(
            agent.state, agent.runtime, "nepadėjo"
        )  # round 3: recap checkpoint first
        assert recap is not None and "Pasitikslinu" in recap
        q = evidence_drive(agent.state, agent.runtime, "taip, viskas taip")
        assert q is not None and "kompiuterį" in q

    def test_refuted_syncs_walker_to_declared_step(self):
        from agent.evidence_drive import evidence_drive
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        agent.state.resolution.procedure["step"] = "dr_intro"  # stale — the rewind trap
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, lemputės dega žaliai")
        # Round 3: a client-stated refute gets ONE confirm question first.
        confirm = evidence_drive(agent.state, agent.runtime, "dega")
        assert confirm is not None and "keičia išvadą" in confirm
        assert evidence_drive(agent.state, agent.runtime, "taip, tikrai dega") is None
        assert agent.state.resolution.procedure["step"] == "dr_cable"  # pivot, not rewind

    def test_pending_key_gives_short_answers_meaning(self):
        from agent.perception_flow import ingest_client_evidence

        # Live 2026-08-10 (T1): "Radau." to "Radote?" carried no noun -> the
        # general extractor was blind -> give-up despite a clear answer.
        agent = _diagnosing_agent()
        agent.state.diagnosis.evidence_ask_counts["device_present"] = 2
        agent.state.diagnosis.pending_evidence_key = "device_present"
        ingest_client_evidence(agent.state, agent.runtime, "Radau.")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"
        assert agent.state.diagnosis.pending_evidence_key is None  # answered — context consumed

    def test_pending_lights_reads_garbled_negation(self):
        from agent.perception_flow import ingest_client_evidence

        # "Ne daganiai 1." (STT of "nedega nė viena") had no 'lemp' word — with
        # the lights question pending it now reads as nedega instead of falling
        # to the stale walker's yes/no classifier (which escalated on it).
        agent = _diagnosing_agent()
        agent.state.diagnosis.pending_evidence_key = "lights"
        ingest_client_evidence(agent.state, agent.runtime, "Ne daganiai 1.")
        assert agent.state.diagnosis.evidence["lights"]["value"] == "off"

    def test_pending_read_overwrites_gave_up_marker(self):
        from agent.evidence import CLIENT, set_fact
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        set_fact(agent.state.diagnosis.evidence, "device_present", "unknown", CLIENT, 3)
        agent.state.diagnosis.pending_evidence_key = "device_present"
        ingest_client_evidence(agent.state, agent.runtime, "Taip, radau tą dėžutę")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"

    def test_pending_read_never_hijacks_other_facts(self):
        from agent.perception_flow import ingest_client_evidence

        # A rich utterance that the general extractor understands wins — the
        # pending context only fills the gap when nothing was extracted.
        agent = _diagnosing_agent()
        agent.state.diagnosis.pending_evidence_key = "device_present"
        ingest_client_evidence(agent.state, agent.runtime, "Radau routerį, lemputės dega žaliai")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"
        assert agent.state.diagnosis.evidence["lights"]["value"] == "on"

    def test_no_ingest_during_ticket_dialogue_or_before_id(self):
        from agent.perception_flow import ingest_client_evidence

        agent = _diagnosing_agent()
        agent.state.ticket.stage = "phone"
        ingest_client_evidence(agent.state, agent.runtime, "Nedega lemputės")
        assert agent.state.diagnosis.evidence == {}
        agent2 = _diagnosing_agent()
        agent2.state.identity.customer_id = None
        ingest_client_evidence(agent2.state, agent2.runtime, "Nedega lemputės")
        assert agent2.state.diagnosis.evidence == {}


class TestFoldedAndNegationAwareReaders:
    """Round 2 (live 2026-08-11): STT drops diacritics ("Tai ikištas",
    "razetė") and glues negations ("Neniauturiu" = "ne, neturiu") — the
    deterministic readers must survive both."""

    def test_negation_prefixed_positive_mark_is_not_a_yes(self):
        from agent.evidence import polarity, read_pending_answer

        # "Neniauturiu." landed has_computer=yes live (substring "turiu").
        assert polarity("Neniauturiu.") != "yes"
        assert read_pending_answer("has_computer", "Neniauturiu.") != "yes"
        # Clean answers still read.
        assert polarity("Turiu kompiuterį") == "yes"
        assert polarity("Ne, neturiu") == "no"
        assert read_pending_answer("has_computer", "turiu") == "yes"

    def test_diacritics_folded_matching(self):
        from agent.evidence import extract_client_facts, read_pending_answer

        assert read_pending_answer("power_cable", "Tai ikistas, viskas gerai") == "plugged"
        assert extract_client_facts("laidas ikistas tvirtai")["power_cable"] == "plugged"
        assert (
            extract_client_facts("kiti irenginiai nuo tos razetes veikia")["outlet_works"]
            == "tried"
        )
