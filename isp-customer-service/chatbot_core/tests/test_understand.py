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


class TestHallucinationGuards:
    """Live 2026-08-10: a question came back with FIVE facts the caller never
    said — the ledger was poisoned and two phantom clarifies followed."""

    def _raw(self, faktai, tipas="atsakymas", conf=0.9):
        return {
            "faktai": faktai,
            "tipas": tipas,
            "supratau": "x",
            "neaiskumas": "",
            "pasitikejimas": conf,
        }

    def test_question_turns_never_carry_facts(self):
        from agent import understand

        raw = self._raw(
            {"device_present": "nerado", "lights": "nedega", "has_computer": "no"},
            tipas="klausimas",
        )
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand(
                "Galim patikrinti, ką man daryti toliau?", anchor="x", needs="", ledger_summary=""
            )
        assert u["faktai"] == {}  # a question does not STATE facts
        assert u["tipas"] == "klausimas"

    def test_low_confidence_facts_dropped(self):
        from agent import understand

        raw = self._raw({"lights": "nedega"}, conf=0.4)
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand("mmm nu gal", anchor="x", needs="", ledger_summary="")
        assert u["faktai"] == {}

    def test_confident_answer_facts_kept(self):
        from agent import understand

        raw = self._raw({"lights": "nedega"}, conf=0.9)
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand("nedega nė viena", anchor="x", needs="", ledger_summary="")
        assert u["faktai"] == {"lights": "nedega"}


class TestRound2Fixes:
    """2026-08-10 round 2: template capture, uncorroborated side entries,
    supplement reads, anchor trimming — each LLM field now has a deterministic
    backer (corroboration / supplement / safe default)."""

    def test_side_entry_requires_corroboration(self, db_connection, monkeypatch):
        # "Galim dabar patikrinti" got tipas=klausimas and froze the engine —
        # no question word, no FAQ hit -> the single sensor may not decide.
        agent = _diagnosing_agent(monkeypatch)
        agent._last_understanding = _canned(tipas="klausimas", supratau="nori patikrinti")
        assert agent.classify_side_topic("Galim dabar patikrinti") is False
        assert agent._side_topic_this_turn is False

    def test_side_entry_allowed_with_question_word(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        agent._last_understanding = _canned(tipas="klausimas", supratau="klausia kainos")
        assert agent.classify_side_topic("O kiek man tai kainuos?") is True

    def test_side_entry_allowed_with_faq_keyword(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        agent._last_understanding = _canned(tipas="klausimas", supratau="klausia apie meistrą")
        assert agent.classify_side_topic("Man atrodo reikės meistro vizito") is True

    def test_supplement_fills_pending_key_on_empty_answer_facts(self, db_connection, monkeypatch):
        # "…sakiau, kad RADAU" came back tipas=atsakymas with faktai={} — the
        # pending-context read now SUPPLEMENTS instead of only falling back.
        agent = _diagnosing_agent(monkeypatch)
        agent._evidence_asks["device_present"] = 2
        agent._evidence_last_ask_key = "device_present"
        with patch(
            "agent.understand.understand",
            return_value=_canned(tipas="atsakymas", supratau="klientas rado routerį"),
        ):
            agent._ingest_client_evidence("Atsiprašau, tik sakiau, kad radau")
        assert agent.state.evidence["device_present"]["value"] == "rado"

    def test_spec_declared_atsakymai_win(self, db_connection, monkeypatch):
        # faults.yaml may declare per-key answer marks — universal for new faults.
        from agent.evidence import read_pending_answer

        item = {"atsakymai": {"nerado": ["nerasiu niekaip"]}}
        assert read_pending_answer("device_present", "nerasiu niekaip čia", item) == "nerado"

    def test_anchor_is_the_question_sentence_only(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        agent.state.last_question = (
            "Patikrinau: internetas iki buto ateina, bet nematome įrenginio. "
            "Dažniausiai tai routeris. Ar patogu dabar patikrinti kartu?"
        )
        assert agent.anchor_text() == "Ar patogu dabar patikrinti kartu?"

    def test_side_facts_carry_deterministic_topic(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        agent.state.last_heard = "O kiek man tai kainuos?"
        agent._last_understanding = _canned(tipas="klausimas", supratau="klausia kainos")
        agent.classify_side_topic("O kiek man tai kainuos?")
        facts = agent._state_facts_block()
        assert "Kliento tema: kaina" in facts  # from the FAQ hit, not a template


class TestTicketUnderstanding:
    """The ticket dialogue reads answers through the pass too (Andrius
    2026-08-10): "Bet kada galima per pietus iš ryto" IS an hours answer —
    the keyword list diverted it on "galima" and the hours defaulted."""

    def _ticket_agent(self, monkeypatch, stage="hours"):
        agent = _diagnosing_agent(monkeypatch)
        agent._begin_ticket_dialogue(None)
        agent._identification_scripted_reply(None)  # asks phone
        if stage == "hours":
            agent._pre_turn_guards("taip, tiks šis")  # keyword consent (pass mocked off below)
            agent._identification_scripted_reply("taip, tiks šis")  # asks hours
        return agent

    def test_hours_with_galima_captured_not_diverted(self, db_connection, monkeypatch):
        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch(
            "agent.understand.understand_ticket",
            return_value={"reiksme": "per pietus arba ryte", "tipas": "atsakymas"},
        ):
            agent._pre_turn_guards("Bet kada galima per pietus iš ryto")
        assert agent.state.contact_hours == "per pietus arba ryte"
        assert agent._ticket_stage == "done"

    def test_phone_tas_pats_via_pass(self, db_connection, monkeypatch):
        agent = self._ticket_agent(monkeypatch, stage="phone")
        with patch(
            "agent.understand.understand_ticket",
            return_value={"reiksme": "tas_pats", "tipas": "atsakymas"},
        ):
            agent._pre_turn_guards("Stengiai tas, iš kurios kambinu")
        assert agent.state.contact_phone == "+37060012353"
        assert agent._ticket_stage == "hours"

    def test_real_question_still_diverts(self, db_connection, monkeypatch):
        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch(
            "agent.understand.understand_ticket",
            return_value={"reiksme": None, "tipas": "klausimas"},
        ):
            agent._pre_turn_guards("O kodėl turiu laukti skambučio?")
        assert agent._ticket_offscript is True
        assert agent.state.contact_hours is None

    def test_pass_failure_falls_back_to_keywords(self, db_connection, monkeypatch):
        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch("agent.understand.understand_ticket", return_value=None):
            agent._pre_turn_guards("po 17 valandos")
        assert agent.state.contact_hours == "po 17 valandos"  # keyword plausibility path

    def test_stale_supratau_cleared_on_ticket_turns(self, db_connection, monkeypatch):
        agent = self._ticket_agent(monkeypatch, stage="hours")
        agent._last_understanding = {"supratau": "Routeris sugedęs", "tipas": "atsakymas"}
        # The stream turn entry clears it for ticket-node turns.
        gen = agent.run_turn_scoped_stream("bet kada", frozenset(), None)
        with patch(
            "agent.understand.understand_ticket",
            return_value={"reiksme": "bet kada", "tipas": "atsakymas"},
        ):
            reply = "".join(gen)
        assert agent._last_understanding is None
        assert "Užregistravau" in reply  # dialogue completed
        facts = agent._state_facts_block() or ""
        assert "Routeris sugedęs" not in facts


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
