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


class TestFindingsAnnounce:
    """2026-08-10: the confirmed moment jumped straight to 'Ar turite
    kompiuterį?' — the caller must first HEAR what was checked, the conclusion
    and the options. Composed from the ledger + faults.yaml (universal)."""

    def _confirmed_agent(self, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        agent._recap_state = "done"  # recap checkpoint tested separately (round 3)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
            agent._ingest_client_evidence("Maitinimo laidas gerai įkištas į rozetę")
            agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        return agent

    def test_announce_precedes_first_solution_question(self, db_connection, monkeypatch):
        agent = self._confirmed_agent(monkeypatch)
        reply = agent._evidence_drive("nepadėjo")
        assert reply is not None
        assert "Ką patikrinome" in reply
        assert "nedega" in reply  # the ledger facts, human-worded
        assert "routeris sugedęs" in reply  # isvada from faults.yaml
        assert "laikinai paleisti internetą per kompiuterį" in reply  # aprasymas
        assert "kompiuterį" in reply.split("Galime:")[-1]  # then the question

    def test_announce_spoken_once(self, db_connection, monkeypatch):
        agent = self._confirmed_agent(monkeypatch)
        first = agent._evidence_drive("nepadėjo")
        second = agent._evidence_drive("dar kartą")
        assert "Ką patikrinome" in first
        assert second is None or "Ką patikrinome" not in second

    def test_announce_prefixes_immediate_ticket(self, db_connection, monkeypatch):
        agent = self._confirmed_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Neturiu kompiuterio, tik telefonas")
        reply = agent._evidence_drive("neturiu")
        assert reply is not None
        assert "Ką patikrinome" in reply
        assert "Kokiu telefono numeriu" in reply  # ticket dialogue follows


class TestConfirmationAgent:
    """Round 3 (Andrius 2026-08-11): 'pasitikslinti, o ne kurti' — the agent
    confirms instead of inventing; checkpoints guard wrong conclusions and
    premature hypothesis rejection."""

    def test_done_report_value_dropped_and_asked_back(self, db_connection, monkeypatch):
        # "Mhm, patikrinau." carried NO result — the pass invented
        # power_cable=atjungtas (echo of the agent's own explanation) and the
        # hypothesis never confirmed (live). The value dies; the drive thanks
        # and asks WHAT was found.
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
        agent._evidence_last_ask_key = "power_cable"
        agent._evidence_asks["power_cable"] = 1
        with patch(
            "agent.understand.understand",
            return_value=_canned(
                faktai={"power_cable": "atjungtas"}, supratau="klientas patikrino laidą", conf=0.8
            ),
        ):
            agent._ingest_client_evidence("Mhm, patikrinau.")
        assert "power_cable" not in agent.state.evidence  # invented value died
        reply = agent._evidence_drive("Mhm, patikrinau.")
        assert reply is not None and "Supratau — patikrinote" in reply
        assert "laidas" in reply  # ka_radote from faults.yaml

    def test_done_report_with_content_still_lands(self, db_connection, monkeypatch):
        # "Taip ir padaryta" to the cable question DOES carry a value ("taip"
        # is the key's own marker) — corroborated, the fact stands.
        agent = _diagnosing_agent(monkeypatch)
        agent._evidence_last_ask_key = "power_cable"
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"power_cable": "įkištas"}, supratau="įkišo laidą"),
        ):
            agent._ingest_client_evidence("Taip ir padaryta")
        assert agent.state.evidence["power_cable"]["value"] == "įkištas"

    def test_facts_recap_precedes_announce(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Radau routerį, nedega nė viena lemputė")
            agent._ingest_client_evidence("Maitinimo laidas gerai įkištas į rozetę")
            agent._ingest_client_evidence("Pabandžiau kitą rozetę, nepadėjo")
        first = agent._evidence_drive("nepadėjo")
        assert first is not None and "Pasitikslinu" in first  # recap question
        assert "nedega" in first  # reads the facts back
        second = agent._evidence_drive("taip, teisingai")
        assert second is not None and "Ką patikrinome" in second  # then announce

    def test_refute_needs_one_confirm_before_pivot(self, db_connection, monkeypatch):
        # A client-stated "dega" refutes the dead-router path — one confirm
        # question before abandoning the hypothesis (STT garbles flip facts).
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Radau, lemputės dega žaliai")
        first = agent._evidence_drive("dega")
        assert first is not None and "keičia išvadą" in first  # refute confirm
        second = agent._evidence_drive("taip, tikrai dega")
        assert second is None  # pivot proceeds (solver/walker takes over)
        assert agent.state.resolution["step"] == "dr_cable"  # paneigta_veda sync


class TestKeywordSupplement:
    """Round 6 (live 2026-08-12): the pass answered with EMPTY faktai (the
    confidence guard wiped a 0.5 read) and the keyword layer never ran — the
    golden 'kiti įrenginiai veikia nuo tos rozetės' lost outlet_works and the
    hypothesis froze. The deterministic layer now ALWAYS supplements."""

    def test_keywords_fill_what_the_pass_dropped(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={}, supratau="bandė kitą rozetę", conf=0.9),
        ):
            agent._ingest_client_evidence(
                "Pabandžiau kitą rozetę, vis tiek neveikia. Kiti įrenginiai nuo tos rozetės veikia."
            )
        assert agent.state.evidence["outlet_works"]["value"] == "bandyta"

    def test_pass_facts_win_on_overlap(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"lights": "mirksi"}, supratau="lemputė mirksi"),
        ):
            agent._ingest_client_evidence("Ta lemputė tai mirksi, čia dega kažkas")
        assert agent.state.evidence["lights"]["value"] == "mirksi"  # pass, not keyword "dega"


class TestGaveUpRevival:
    def test_blocking_neaisku_key_gets_one_revival(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact

        agent = _diagnosing_agent(monkeypatch)
        set_fact(agent.state.evidence, "device_present", "rado", CLIENT, 1)
        set_fact(agent.state.evidence, "lights", "nedega", CLIENT, 2)
        set_fact(agent.state.evidence, "power_cable", "neaišku", CLIENT, 3)  # gave up
        reply = agent._evidence_drive("nežinau")
        assert reply is not None and "maitinimo laidas" in reply  # the revival names it
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Dabar pažiūrėjau — įkištas gerai, tvirtai")
        assert agent.state.evidence["power_cable"]["value"] == "įkištas"
        follow_up = agent._evidence_drive("įkištas gerai")
        assert follow_up is not None and "rozet" in follow_up  # the plan resumes

    def test_revival_happens_once_then_hands_over(self, db_connection, monkeypatch):
        from agent.evidence import CLIENT, set_fact

        agent = _diagnosing_agent(monkeypatch)
        set_fact(agent.state.evidence, "device_present", "rado", CLIENT, 1)
        set_fact(agent.state.evidence, "lights", "nedega", CLIENT, 2)
        set_fact(agent.state.evidence, "power_cable", "neaišku", CLIENT, 3)
        assert agent._evidence_drive("nežinau") is not None  # revival
        set_fact(agent.state.evidence, "power_cable", "neaišku", CLIENT, 4)  # still unreadable
        assert agent._evidence_drive("nežinau") is None  # hands over, no loop


class TestContradictionCorroboration:
    def test_uncorroborated_flip_dropped(self, db_connection, monkeypatch):
        # "Neturi kompiuterio" hallucinated device_present=nerado against a
        # settled "rado" — the keyword layer sees no such flip -> dropped.
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Radau routerį prie lango")
        assert agent.state.evidence["device_present"]["value"] == "rado"
        with patch(
            "agent.understand.understand",
            return_value=_canned(
                faktai={"device_present": "nerado", "has_computer": "no"},
                supratau="klientas neturi kompiuterio",
            ),
        ):
            agent._ingest_client_evidence("Neturi kompiuterio.")
        e = agent.state.evidence["device_present"]
        assert e["value"] == "rado" and e["conflict"] is False  # phantom died
        assert agent.state.evidence["has_computer"]["value"] == "no"  # real fact landed

    def test_corroborated_flip_still_opens_conflict(self, db_connection, monkeypatch):
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("Nedega nė viena lemputė")
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"lights": "dega"}, supratau="lemputė užsidegė"),
        ):
            agent._ingest_client_evidence("O, dabar lemputė dega!")
        e = agent.state.evidence["lights"]
        assert e["conflict"] is True  # keywords agree -> the clarify machinery runs

    def test_flip_corroborated_by_key_own_markers(self, db_connection, monkeypatch):
        # Live 2026-08-11: ledger had power_cable=atjungtas (from "routeris
        # neturi maitinimo"); the caller then answered "Tai ikištas" WITHOUT
        # the topic word "laidas" — the general extractor saw no cable topic
        # and the TRUE update was dropped, so the hypothesis never confirmed
        # and the findings announce never fired. The key's OWN answer markers
        # (read_pending_answer) now corroborate the flip.
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.understand.understand",
            return_value=_canned(
                faktai={"power_cable": "atjungtas"}, supratau="routeris be maitinimo"
            ),
        ):
            agent._ingest_client_evidence("routeris neturi maitinimo")
        assert agent.state.evidence["power_cable"]["value"] == "atjungtas"
        with patch(
            "agent.understand.understand",
            return_value=_canned(faktai={"power_cable": "įkištas"}, supratau="laidas įkištas"),
        ):
            agent._ingest_client_evidence("Tai ikištas, viskas gerai")  # STT dropped į
        e = agent.state.evidence["power_cable"]
        assert e["conflict"] is True  # accepted -> ONE clarify settles it


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
