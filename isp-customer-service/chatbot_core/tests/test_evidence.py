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
        set_fact(ev, "lights", "nedega", CLIENT, 2)
        entry = set_fact(ev, "lights", "nedega", CLIENT, 4)
        assert entry["conflict"] is False and entry["turn"] == 4


class TestExtraction:
    def test_core_no_mac_facts(self):
        from agent.evidence import extract_client_facts as x

        assert x("Neturi kompiutera, tik telefonas") == {"has_computer": "no"}
        assert x("Turiu kompiuterį namuose")["has_computer"] == "yes"
        assert x("Nedega nė viena lemputė")["lights"] == "nedega"
        assert x("Lemputės dega žaliai")["lights"] == "dega"
        assert x("Lemputė mirksi raudonai")["lights"] == "mirksi"
        assert x("Maitinimo laidas gerai įkištas į rozetę")["power_cable"] == "įkištas"
        assert x("Kabelis buvo atjungtas nuo routerio")["power_cable"] == "atjungtas"
        assert x("Pabandžiau kitą rozetę, nepadėjo")["outlet_works"] == "bandyta"
        assert x("Radau tą routerio dėžutę su antena")["device_present"] == "rado"

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
        assert facts["lights"] == "nedega"
        assert facts["device_present"] == "rado"

    def test_real_value_replaces_gave_up_marker_without_conflict(self):
        from agent.evidence import CLIENT, set_fact

        ev = {}
        set_fact(ev, "power_cable", "neaišku", CLIENT, 5)  # give-up marker
        entry = set_fact(ev, "power_cable", "įkištas", CLIENT, 7)
        assert entry["value"] == "įkištas" and entry["conflict"] is False

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
    from agent.react_agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060012353", tracer=_CaptureTracer())
    agent.state.customer_id = "CUST009"
    agent.state.problem_type = "internet_down"
    agent.state.hypothesis = {
        "cause": "no_mac_observed",
        "status": "testing",
        "because": ["linijoje nematomas įrenginys"],
    }
    agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}
    return agent


class TestAgentWiring:
    def test_telemetry_verdict_lands_on_ledger(self):
        agent = _diagnosing_agent()
        obs = json.dumps({"verdict": {"reason": "no_mac_observed", "side": "unclear"}})
        agent._update_state_from_observation("diagnose_connection", obs)
        assert agent.state.evidence["verdict"]["value"] == "no_mac_observed"
        assert agent.state.evidence["verdict"]["source"] == "telemetry"

    def test_ingest_fills_client_facts(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Nedega nė viena lemputė, laidas įkištas")
        assert agent.state.evidence["lights"]["value"] == "nedega"
        assert agent.state.evidence["power_cable"]["value"] == "įkištas"

    def test_contradiction_asks_one_clarify_then_settles(self):
        from agent.identification import phrase

        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Neturiu kompiuterio, tik telefonas")
        agent._ingest_client_evidence("Turiu kompiuterį, galim bandyti")
        assert agent._evidence_conflict is not None
        # The solver yields, the walker holds, the scripted clarify goes out.
        assert agent.solver_drive_turn("Turiu kompiuterį, galim bandyti") is None
        agent._advance_resolution("Turiu kompiuterį, galim bandyti")
        assert agent.state.resolution["step"] == "dr_lights"  # held, not advanced
        reply = agent._identification_scripted_reply("Turiu kompiuterį, galim bandyti")
        assert reply == phrase(
            "evidence_conflict", tema="ar turite kompiuterį", a="neturite", b="turite"
        )
        # The settling answer resolves the fact; no second clarify.
        agent._ingest_client_evidence("Turiu kompiuterį")
        e = agent.state.evidence["has_computer"]
        assert e["value"] == "yes" and e["conflict"] is False
        assert agent._evidence_conflict is None and agent._evidence_conflict_asked is None

    def test_bare_polarity_settles_yes_no_conflict(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Neturiu kompiuterio, tik telefonas")
        agent._ingest_client_evidence("Turiu kompiuterį vis dėlto")
        agent._identification_scripted_reply("x")  # asks the clarify
        agent._ingest_client_evidence("Taip.")  # bare yes
        assert agent.state.evidence["has_computer"]["value"] == "yes"

    def test_unreadable_settle_keeps_latest_and_stops_asking(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Neturiu kompiuterio, tik telefonas")
        agent._ingest_client_evidence("Turiu kompiuterį vis dėlto")
        agent._identification_scripted_reply("x")
        agent._ingest_client_evidence("Kurs komentai")  # garble
        e = agent.state.evidence["has_computer"]
        assert e["conflict"] is False and e["value"] == "yes"  # latest stated wins
        assert agent._evidence_conflict_asked is None

    def test_facts_block_and_solver_context_carry_ledger(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Nedega nė viena lemputė")
        facts = agent._state_facts_block()
        assert facts and "ĮRODYMŲ ŽURNALAS" in facts and "nedega" in facts
        ctx = agent._build_solver_context("tęsiam")
        assert "ĮRODYMŲ ŽURNALAS" in ctx

    def test_ticket_carries_client_evidence(self, db_connection):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Nedega nė viena lemputė")
        agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        agent.state.contact_phone = "+37060012353"
        agent.state.contact_hours = "bet kada"
        agent._register_ticket_from_state(None)
        assert agent.state.ticket_id
        with db_connection.cursor() as cur:
            cur.execute("SELECT details FROM tickets WHERE ticket_id = ?", (agent.state.ticket_id,))
            details = dict(cur.fetchone())["details"]
        assert "Patikrinta su klientu" in details
        assert "routerio lemputės: nedega" in details
        assert "rozetė: bandyta" in details

    def test_spec_and_need_load_from_faults_yaml(self):
        from agent.evidence import fault_need, spec_for

        spec = spec_for("no_mac_observed")
        assert spec is not None
        assert list(spec["client"]) == [
            "device_present",
            "lights",
            "power_cable",
            "outlet_works",
            "has_computer",
        ]
        assert fault_need("no_mac_observed") == "reikalingas naujas maršrutizatorius"
        assert spec_for("nesamas_verdiktas") is None

    def test_evidence_drive_asks_in_order_with_kada_gates(self):
        agent = _diagnosing_agent()
        # Nothing known -> the first question is device_present (lights is gated).
        q1 = agent._evidence_drive("galim patikrinti")
        assert "Susiraskite routerį" in q1
        agent._ingest_client_evidence("Radau tą routerio dėžutę su antena")
        q2 = agent._evidence_drive("radau")
        assert "bent viena lemputė" in q2
        agent._ingest_client_evidence("Nedega nė viena lemputė")
        q3 = agent._evidence_drive("nedega")
        assert "maitinimo laidas" in q3

    def test_unreadable_answers_escalate_wording_then_give_up(self):
        agent = _diagnosing_agent()
        q1 = agent._evidence_drive("x")
        assert "Susiraskite routerį" in q1  # level 1
        q2 = agent._evidence_drive("Kurs komentai")  # extractor got nothing
        assert "dėžutės su lemputėmis" in q2  # paprasciau (level 2)
        q3 = agent._evidence_drive("Vis tiek nesuprantu")
        # Gave up on device_present -> recorded "neaišku"; lights stays gated
        # (kada: device_present=rado), so nothing left to ask -> solver's turn.
        assert agent.state.evidence["device_present"]["value"] == "neaišku"
        assert q3 is None

    def test_confirmed_with_no_computer_escalates_to_ticket(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._ingest_client_evidence("Maitinimo laidas gerai įkištas į rozetę")
        agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        agent._ingest_client_evidence("Neturiu kompiuterio, tik telefonas")
        # Round 3: the first confirmed moment READS THE FACTS BACK first.
        recap = agent._evidence_drive("neturiu")
        assert recap is not None and "Pasitikslinu" in recap
        reply = agent._evidence_drive("taip, teisingai")
        assert reply is not None and "Kokiu telefono numeriu" in reply
        assert agent._ticket_stage == "phone"

    def test_confirmed_with_computer_yields_to_solver_bridge(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._ingest_client_evidence("Maitinimo laidas gerai įkištas į rozetę")
        agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        agent._ingest_client_evidence("Turiu kompiuterį")
        recap = agent._evidence_drive("turiu")  # round 3: recap checkpoint first
        assert recap is not None and "Pasitikslinu" in recap
        assert agent._evidence_drive("taip") is None  # then solver drives the bridge

    def test_confirmed_but_device_unknown_asks_has_computer(self):
        agent = _diagnosing_agent()
        agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._ingest_client_evidence("Maitinimo laidas gerai įkištas į rozetę")
        agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        recap = agent._evidence_drive("nepadėjo")  # round 3: recap checkpoint first
        assert recap is not None and "Pasitikslinu" in recap
        q = agent._evidence_drive("taip, viskas taip")
        assert q is not None and "kompiuterį" in q

    def test_refuted_syncs_walker_to_declared_step(self):
        agent = _diagnosing_agent()
        agent.state.resolution["step"] = "dr_intro"  # stale — the rewind trap
        agent._ingest_client_evidence("Radau routerį, lemputės dega žaliai")
        # Round 3: a client-stated refute gets ONE confirm question first.
        confirm = agent._evidence_drive("dega")
        assert confirm is not None and "keičia išvadą" in confirm
        assert agent._evidence_drive("taip, tikrai dega") is None
        assert agent.state.resolution["step"] == "dr_cable"  # pivot, not rewind

    def test_pending_key_gives_short_answers_meaning(self):
        # Live 2026-08-10 (T1): "Radau." to "Radote?" carried no noun -> the
        # general extractor was blind -> give-up despite a clear answer.
        agent = _diagnosing_agent()
        agent._evidence_asks["device_present"] = 2
        agent._evidence_last_ask_key = "device_present"
        agent._ingest_client_evidence("Radau.")
        assert agent.state.evidence["device_present"]["value"] == "rado"
        assert agent._evidence_last_ask_key is None  # answered — context consumed

    def test_pending_lights_reads_garbled_negation(self):
        # "Ne daganiai 1." (STT of "nedega nė viena") had no 'lemp' word — with
        # the lights question pending it now reads as nedega instead of falling
        # to the stale walker's yes/no classifier (which escalated on it).
        agent = _diagnosing_agent()
        agent._evidence_last_ask_key = "lights"
        agent._ingest_client_evidence("Ne daganiai 1.")
        assert agent.state.evidence["lights"]["value"] == "nedega"

    def test_pending_read_overwrites_gave_up_marker(self):
        from agent.evidence import CLIENT, set_fact

        agent = _diagnosing_agent()
        set_fact(agent.state.evidence, "device_present", "neaišku", CLIENT, 3)
        agent._evidence_last_ask_key = "device_present"
        agent._ingest_client_evidence("Taip, radau tą dėžutę")
        assert agent.state.evidence["device_present"]["value"] == "rado"

    def test_pending_read_never_hijacks_other_facts(self):
        # A rich utterance that the general extractor understands wins — the
        # pending context only fills the gap when nothing was extracted.
        agent = _diagnosing_agent()
        agent._evidence_last_ask_key = "device_present"
        agent._ingest_client_evidence("Radau routerį, lemputės dega žaliai")
        assert agent.state.evidence["device_present"]["value"] == "rado"
        assert agent.state.evidence["lights"]["value"] == "dega"

    def test_no_ingest_during_ticket_dialogue_or_before_id(self):
        agent = _diagnosing_agent()
        agent._ticket_stage = "phone"
        agent._ingest_client_evidence("Nedega lemputės")
        assert agent.state.evidence == {}
        agent2 = _diagnosing_agent()
        agent2.state.customer_id = None
        agent2._ingest_client_evidence("Nedega lemputės")
        assert agent2.state.evidence == {}


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

        assert read_pending_answer("power_cable", "Tai ikistas, viskas gerai") == "įkištas"
        assert extract_client_facts("laidas ikistas tvirtai")["power_cable"] == "įkištas"
        assert (
            extract_client_facts("kiti irenginiai nuo tos razetes veikia")["outlet_works"]
            == "bandyta"
        )
