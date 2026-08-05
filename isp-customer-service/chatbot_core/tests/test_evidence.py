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

    def test_no_ingest_during_ticket_dialogue_or_before_id(self):
        agent = _diagnosing_agent()
        agent._ticket_stage = "phone"
        agent._ingest_client_evidence("Nedega lemputės")
        assert agent.state.evidence == {}
        agent2 = _diagnosing_agent()
        agent2.state.customer_id = None
        agent2._ingest_client_evidence("Nedega lemputės")
        assert agent2.state.evidence == {}
