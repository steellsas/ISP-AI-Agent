"""SUPRATIMO pass'as (Ledger v2.5) — the understanding layer.

The model call is mocked; CLASSIFIER=off (conftest) disables the pass in every
other test file, so the deterministic suite is untouched.

Run: pytest tests/test_understand.py -v
"""

import json
from unittest.mock import patch

import pytest


def _diagnosing_agent(monkeypatch, understand_on=True):
    import os

    from agent.react_agent import ReactAgent

    if understand_on:
        monkeypatch.setitem(os.environ, "CLASSIFIER", "on")
        monkeypatch.setitem(os.environ, "UNDERSTAND", "on")
    agent = ReactAgent(caller_phone="+37060012353")
    agent.state.customer_id = "CUST009"
    agent.state.problem_type = "internet_down"
    agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights", "asked": True}
    agent.state.last_question = "Susiraskite routerį — dėžutę. Radote?"
    return agent


def _canned(faktai=None, tipas="atsakymas", supratau="", neaiskumas="", conf=0.9):
    return {
        "faktai": faktai or {},
        "tipas": tipas,
        "supratau": supratau,
        "neaiskumas": neaiskumas,
        "pasitikejimas": conf,
    }


class TestUnderstandModule:
    def test_disabled_under_classifier_off(self, monkeypatch):
        import os

        from agent import understand

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        assert understand.enabled() is False

    def test_validates_facts_against_allowed_values(self, monkeypatch):
        from agent import understand

        raw = {
            "faktai": {"lights": "nedega", "lights_color": "raudona", "has_computer": "gal"},
            "tipas": "atsakymas",
            "supratau": "lemputės nedega",
            "neaiskumas": "",
            "pasitikejimas": 0.9,
        }
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand(
                "ne daganiai viena", anchor="Ar dega lemputės?", needs="", ledger_summary=""
            )
        assert u["faktai"] == {"lights": "nedega"}  # unknown key + value dropped

    def test_any_failure_returns_none(self, monkeypatch):
        from agent import understand

        with patch(
            "src.services.llm.client.llm_json_completion", side_effect=RuntimeError("api down")
        ):
            assert (
                understand.understand("radau", anchor="Radote?", needs="", ledger_summary="")
                is None
            )


class TestUnderstandWiring:
    def test_understanding_facts_land_on_ledger(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(faktai={"device_present": "rado"}, supratau="klientas rado routerį")
        with patch("agent.understand.understand", return_value=canned):
            agent._ingest_client_evidence("Radau.")
        assert agent.state.evidence["device_present"]["value"] == "rado"
        assert agent._last_understanding["supratau"] == "klientas rado routerį"

    def test_pass_failure_falls_back_to_keywords(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Nedega nė viena lemputė")
        assert agent.state.evidence["lights"]["value"] == "nedega"  # keyword layer caught it

    def test_tipas_klausimas_routes_to_side_topic(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(tipas="klausimas", supratau="klausia kainos")
        with patch("agent.understand.understand", return_value=canned):
            agent._ingest_client_evidence("O kiek man tai kainuos?")
        assert agent.classify_side_topic("O kiek man tai kainuos?") is True

    def test_tipas_nesupratimas_is_not_a_deviation_and_directs_reexplain(
        self, db_connection, monkeypatch
    ):
        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(
            tipas="nesupratimas",
            supratau="klientas neranda routerio",
            neaiskumas="nežino, kuri dėžutė yra routeris",
        )
        with patch("agent.understand.understand", return_value=canned):
            agent._ingest_client_evidence("Nu nerandu aš čia nieko, kur ta dėžutė?")
        assert agent.classify_side_topic("Nu nerandu aš čia nieko, kur ta dėžutė?") is False
        facts = agent._state_facts_block()
        assert "KLIENTAS NESUPRATO" in facts and "kuri dėžutė" in facts
        assert "PATVIRTINK" in facts

    def test_acknowledgement_directive_carries_supratau(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(faktai={"lights": "nedega"}, supratau="lemputės nedega")
        with patch("agent.understand.understand", return_value=canned):
            agent._ingest_client_evidence("ne daganiai viena")
        facts = agent._state_facts_block()
        assert "PATVIRTINK" in facts and "lemputės nedega" in facts

    def test_contradiction_from_pass_flows_into_conflict_machinery(
        self, db_connection, monkeypatch
    ):
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"has_computer": "no"}),
        ):
            agent._ingest_client_evidence("Neturiu kompiuterio")
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"has_computer": "yes"}, tipas="prieštaravimas"),
        ):
            agent._ingest_client_evidence("Turiu kompiuterį")
        assert agent._evidence_conflict is not None  # same clarify discipline as before

    def test_keyword_suite_untouched_without_flag(self, db_connection, monkeypatch):
        # CLASSIFIER=off (the whole deterministic suite) — the pass never runs.
        import os

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = _diagnosing_agent(monkeypatch, understand_on=False)
        called = {"v": False}

        def _boom(*a, **k):
            called["v"] = True
            return None

        with patch("agent.understand.understand", side_effect=_boom):
            agent._ingest_client_evidence("Nedega nė viena lemputė")
        assert called["v"] is False
        assert agent.state.evidence["lights"]["value"] == "nedega"
