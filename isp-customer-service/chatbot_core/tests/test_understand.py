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

    from tests.calls import make_agent

    if understand_on:
        monkeypatch.setitem(os.environ, "CLASSIFIER", "on")
        monkeypatch.setitem(os.environ, "UNDERSTAND", "on")
    agent = make_agent("+37060012353")
    agent.state.identity.customer_id = "CUST009"
    agent.state.intake.problem_type = "internet_down"
    agent.state.resolution.procedure = {
        "verdict": "no_mac_observed",
        "step": "dr_lights",
        "asked": True,
    }
    agent.state.dialog.last_question = "Susiraskite routerį — dėžutę. Radote?"
    return agent


def _canned(facts=None, turn_type="answer", understood="", confusion="", conf=0.9):
    return {
        "facts": facts or {},
        "type": turn_type,
        "understood": understood,
        "confusion": confusion,
        "confidence": conf,
    }


class TestUnderstandModule:
    def test_disabled_under_classifier_off(self, monkeypatch):
        import os

        from agent.perceive import understand

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        assert understand.enabled() is False

    def test_validates_facts_against_allowed_values(self, monkeypatch):
        from agent.perceive import understand

        raw = {
            "facts": {"lights": "off", "lights_color": "raudona", "has_computer": "gal"},
            "type": "answer",
            "understood": "lemputės nedega",
            "confusion": "",
            "confidence": 0.9,
        }
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand(
                "ne daganiai viena", anchor="Ar dega lemputės?", needs="", ledger_summary=""
            )
        assert u["facts"] == {"lights": "off"}  # unknown key + value dropped

    def test_any_failure_returns_none(self, monkeypatch):
        from agent.perceive import understand

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

    def _raw(self, facts, turn_type="answer", conf=0.9):
        return {
            "facts": facts,
            "type": turn_type,
            "understood": "x",
            "confusion": "",
            "confidence": conf,
        }

    def test_question_turns_never_carry_facts(self):
        from agent.perceive import understand

        raw = self._raw(
            {"device_present": "not_found", "lights": "off", "has_computer": "no"},
            turn_type="question",
        )
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand(
                "Galim patikrinti, ką man daryti toliau?", anchor="x", needs="", ledger_summary=""
            )
        assert u["facts"] == {}  # a question does not STATE facts
        assert u["type"] == "question"

    def test_low_confidence_facts_dropped(self):
        from agent.perceive import understand

        raw = self._raw({"lights": "off"}, conf=0.4)
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand("mmm nu gal", anchor="x", needs="", ledger_summary="")
        assert u["facts"] == {}

    def test_confident_answer_facts_kept(self):
        from agent.perceive import understand

        raw = self._raw({"lights": "off"}, conf=0.9)
        with patch("src.services.llm.client.llm_json_completion", return_value=raw):
            u = understand.understand("nedega nė viena", anchor="x", needs="", ledger_summary="")
        assert u["facts"] == {"lights": "off"}


class TestRound2Fixes:
    """2026-08-10 round 2: template capture, uncorroborated side entries,
    supplement reads, anchor trimming — each LLM field now has a deterministic
    backer (corroboration / supplement / safe default)."""

    def test_side_entry_requires_corroboration(self, db_connection, monkeypatch):
        from agent.perceive.side_topic import classify_side_topic

        # "Galim dabar patikrinti" got tipas=klausimas and froze the engine —
        # no question word, no FAQ hit -> the single sensor may not decide.
        agent = _diagnosing_agent(monkeypatch)
        agent.state.turn.understanding = _canned(turn_type="question", understood="nori patikrinti")
        assert classify_side_topic(agent.state, agent.runtime, "Galim dabar patikrinti") is False
        assert agent.state.turn.side_topic_active is False

    def test_side_entry_allowed_with_question_word(self, db_connection, monkeypatch):
        from agent.perceive.side_topic import classify_side_topic

        agent = _diagnosing_agent(monkeypatch)
        agent.state.turn.understanding = _canned(turn_type="question", understood="klausia kainos")
        assert classify_side_topic(agent.state, agent.runtime, "O kiek man tai kainuos?") is True

    def test_side_entry_allowed_with_faq_keyword(self, db_connection, monkeypatch):
        from agent.perceive.side_topic import classify_side_topic

        agent = _diagnosing_agent(monkeypatch)
        agent.state.turn.understanding = _canned(
            turn_type="question", understood="klausia apie meistrą"
        )
        assert (
            classify_side_topic(agent.state, agent.runtime, "Man atrodo reikės meistro vizito")
            is True
        )

    def test_supplement_fills_pending_key_on_empty_answer_facts(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        # "…sakiau, kad RADAU" came back tipas=atsakymas with facts={} — the
        # pending-context read now SUPPLEMENTS instead of only falling back.
        agent = _diagnosing_agent(monkeypatch)
        agent.state.diagnosis.evidence_ask_counts["device_present"] = 2
        agent.state.diagnosis.pending_evidence_key = "device_present"
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(turn_type="answer", understood="klientas rado routerį"),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Atsiprašau, tik sakiau, kad radau")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"

    def test_spec_declared_atsakymai_win(self, db_connection, monkeypatch):
        # faults.yaml may declare per-key answer marks — universal for new faults.
        from agent.evidence import read_pending_answer

        item = {"answers": {"nerado": ["nerasiu niekaip"]}}
        assert read_pending_answer("device_present", "nerasiu niekaip čia", item) == "nerado"

    def test_anchor_is_the_question_sentence_only(self, db_connection, monkeypatch):
        from agent.dialog_utils import anchor_text

        agent = _diagnosing_agent(monkeypatch)
        agent.state.dialog.last_question = (
            "Patikrinau: internetas iki buto ateina, bet nematome įrenginio. "
            "Dažniausiai tai routeris. Ar patogu dabar patikrinti kartu?"
        )
        assert anchor_text(agent.state, agent.runtime) == "Ar patogu dabar patikrinti kartu?"

    def test_side_facts_carry_deterministic_topic(self, db_connection, monkeypatch):
        from agent.perceive.side_topic import classify_side_topic
        from agent.speak.context_card import context_card

        agent = _diagnosing_agent(monkeypatch)
        agent.state.dialog.last_heard = "O kiek man tai kainuos?"
        agent.state.turn.understanding = _canned(turn_type="question", understood="klausia kainos")
        classify_side_topic(agent.state, agent.runtime, "O kiek man tai kainuos?")
        facts = context_card(agent.state, agent.runtime)
        assert "The caller's topic: kaina" in facts  # from the FAQ hit, not a template


class TestFindingsAnnounce:
    """2026-08-10: the confirmed moment jumped straight to 'Ar turite
    kompiuterį?' — the caller must first HEAR what was checked, the conclusion
    and the options. Composed from the ledger + faults.yaml (universal)."""

    def _confirmed_agent(self, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        agent.state.diagnosis.facts_recap_state = (
            "done"  # recap checkpoint tested separately (round 3)
        )
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(
                agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė"
            )
            ingest_client_evidence(
                agent.state, agent.runtime, "Maitinimo laidas gerai įkištas į rozetę"
            )
            ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        return agent

    def test_announce_precedes_first_solution_question(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        agent = self._confirmed_agent(monkeypatch)
        reply = evidence_drive(agent.state, agent.runtime, "nepadėjo")
        assert reply is not None
        assert "Ką patikrinome" in reply
        assert "nedega" in reply  # the ledger facts, human-worded
        assert "routeris sugedęs" in reply  # isvada from faults.yaml
        assert "laikinai paleisti internetą per kompiuterį" in reply  # aprasymas
        assert "kompiuterį" in reply.split("Galime:")[-1]  # then the question

    def test_announce_spoken_once(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive

        agent = self._confirmed_agent(monkeypatch)
        first = evidence_drive(agent.state, agent.runtime, "nepadėjo")
        second = evidence_drive(agent.state, agent.runtime, "dar kartą")
        assert "Ką patikrinome" in first
        assert second is None or "Ką patikrinome" not in second

    def test_announce_prefixes_immediate_ticket(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.perceive.evidence import ingest_client_evidence

        agent = self._confirmed_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio, tik telefonas")
        reply = evidence_drive(agent.state, agent.runtime, "neturiu")
        assert reply is not None
        assert "Ką patikrinome" in reply
        assert "Ar tiks numeris" in reply  # ticket dialogue follows


class TestConfirmationAgent:
    """Round 3 (Andrius 2026-08-11): 'pasitikslinti, o ne kurti' — the agent
    confirms instead of inventing; checkpoints guard wrong conclusions and
    premature hypothesis rejection."""

    def test_done_report_value_dropped_and_asked_back(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.perceive.evidence import ingest_client_evidence

        # "Mhm, patikrinau." carried NO result — the pass invented
        # power_cable=atjungtas (echo of the agent's own explanation) and the
        # hypothesis never confirmed (live). The value dies; the drive thanks
        # and asks WHAT was found.
        agent = _diagnosing_agent(monkeypatch)
        from agent.evidence import CLIENT, set_fact

        set_fact(agent.state.diagnosis.evidence, "recent_events", "no", CLIENT, 0)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(
                agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė"
            )
        agent.state.diagnosis.pending_evidence_key = "power_cable"
        agent.state.diagnosis.evidence_ask_counts["power_cable"] = 1
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(
                facts={"power_cable": "unplugged"}, understood="klientas patikrino laidą", conf=0.8
            ),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Mhm, patikrinau.")
        assert "power_cable" not in agent.state.diagnosis.evidence  # invented value died
        reply = evidence_drive(agent.state, agent.runtime, "Mhm, patikrinau.")
        assert reply is not None and "Supratau — patikrinote" in reply
        assert "laidas" in reply  # ka_radote from faults.yaml

    def test_done_report_with_content_still_lands(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        # "Taip ir padaryta" to the cable question DOES carry a value ("taip"
        # is the key's own marker) — corroborated, the fact stands.
        agent = _diagnosing_agent(monkeypatch)
        agent.state.diagnosis.pending_evidence_key = "power_cable"
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"power_cable": "plugged"}, understood="įkišo laidą"),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Taip ir padaryta")
        assert agent.state.diagnosis.evidence["power_cable"]["value"] == "plugged"

    def test_facts_recap_precedes_announce(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(
                agent.state, agent.runtime, "Radau routerį, nedega nė viena lemputė"
            )
            ingest_client_evidence(
                agent.state, agent.runtime, "Maitinimo laidas gerai įkištas į rozetę"
            )
            ingest_client_evidence(agent.state, agent.runtime, "Pabandžiau kitą rozetę, nepadėjo")
        first = evidence_drive(agent.state, agent.runtime, "nepadėjo")
        assert first is not None and "Pasitikslinu" in first  # recap question
        assert "nedega" in first  # reads the facts back
        second = evidence_drive(agent.state, agent.runtime, "taip, teisingai")
        assert second is not None and "Ką patikrinome" in second  # then announce

    def test_refute_needs_one_confirm_before_pivot(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.perceive.evidence import ingest_client_evidence

        # A client-stated "dega" refutes the dead-router path — one confirm
        # question before abandoning the hypothesis (STT garbles flip facts).
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(agent.state, agent.runtime, "Radau, lemputės dega žaliai")
        first = evidence_drive(agent.state, agent.runtime, "dega")
        assert first is not None and "keičia išvadą" in first  # refute confirm
        second = evidence_drive(agent.state, agent.runtime, "taip, tikrai dega")
        assert second is None  # pivot proceeds (solver/walker takes over)
        assert agent.state.resolution.procedure["step"] == "dr_cable"  # paneigta_veda sync


class TestKeywordSupplement:
    """Round 6 (live 2026-08-12): the pass answered with EMPTY faktai (the
    confidence guard wiped a 0.5 read) and the keyword layer never ran — the
    golden 'kiti įrenginiai veikia nuo tos rozetės' lost outlet_works and the
    hypothesis froze. The deterministic layer now ALWAYS supplements."""

    def test_keywords_fill_what_the_pass_dropped(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={}, understood="bandė kitą rozetę", conf=0.9),
        ):
            ingest_client_evidence(
                agent.state,
                agent.runtime,
                "Pabandžiau kitą rozetę, vis tiek neveikia. Kiti įrenginiai nuo tos rozetės veikia.",
            )
        assert agent.state.diagnosis.evidence["outlet_works"]["value"] == "tried"

    def test_agreeing_readers_land_one_clean_fact(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"lights": "blinking"}, understood="lemputė mirksi"),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Ta lemputė tai mirksi")
        e = agent.state.diagnosis.evidence["lights"]
        assert e["value"] == "blinking" and e["conflict"] is False

    def test_disagreeing_readers_open_a_conflict(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"lights": "blinking"}, understood="lemputė mirksi"),
        ):
            ingest_client_evidence(
                agent.state, agent.runtime, "Lemputė dega žaliai"
            )  # keywords read DEGA
        e = agent.state.diagnosis.evidence["lights"]
        assert e["conflict"] is True  # neither reader wins silently

    def test_reader_disagreement_on_fresh_key_asks_clarify(self, db_connection, monkeypatch):
        from agent.decide.rules.reply import scripted_words
        from agent.perceive.evidence import ingest_client_evidence

        # Live 2026-08-12: "kiti įrenginiai veikia nuo tos rozetės, bet
        # ROUTERIS neveikia" — the pass pinned neveikia on the OUTLET while
        # keywords read the correct bandyta; the silent pass win skipped the
        # recap and the announce. Now: conflict -> ONE clarify -> settled.
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(
                facts={"outlet_works": "not_working"}, understood="rozetė neveikia"
            ),
        ):
            ingest_client_evidence(
                agent.state,
                agent.runtime,
                "Pabandžiau kitą rozetę — kiti įrenginiai veikia, bet routeris neveikia.",
            )
        e = agent.state.diagnosis.evidence["outlet_works"]
        assert e["conflict"] is True  # neither reader won silently
        assert agent.state.diagnosis.contradiction is not None  # the clarify goes out
        with patch("agent.perceive.understand.understand", return_value=None):
            reply = scripted_words(agent.state, agent.runtime, "na")
        assert reply is not None and "rozetė" in reply  # "kaip yra iš tiesų?"


class TestGaveUpRevival:
    def test_blocking_neaisku_key_gets_one_revival(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.evidence import CLIENT, set_fact
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        set_fact(agent.state.diagnosis.evidence, "recent_events", "no", CLIENT, 0)
        set_fact(agent.state.diagnosis.evidence, "device_present", "found", CLIENT, 1)
        set_fact(agent.state.diagnosis.evidence, "lights", "off", CLIENT, 2)
        set_fact(agent.state.diagnosis.evidence, "power_cable", "unknown", CLIENT, 3)  # gave up
        reply = evidence_drive(agent.state, agent.runtime, "nežinau")
        # C 2026-08-20: reask_reason no longer reads internal labels back —
        # the topic is still named through the patikslinimas question itself.
        assert reply is not None and "laidas" in reply  # the revival names it
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(
                agent.state, agent.runtime, "Dabar pažiūrėjau — įkištas gerai, tvirtai"
            )
        assert agent.state.diagnosis.evidence["power_cable"]["value"] == "plugged"
        follow_up = evidence_drive(agent.state, agent.runtime, "įkištas gerai")
        assert follow_up is not None and "rozet" in follow_up  # the plan resumes

    def test_revival_happens_once_then_hands_over(self, db_connection, monkeypatch):
        from agent.decide.rules.evidence import evidence_drive
        from agent.evidence import CLIENT, set_fact

        agent = _diagnosing_agent(monkeypatch)
        set_fact(agent.state.diagnosis.evidence, "recent_events", "no", CLIENT, 0)
        set_fact(agent.state.diagnosis.evidence, "device_present", "found", CLIENT, 1)
        set_fact(agent.state.diagnosis.evidence, "lights", "off", CLIENT, 2)
        set_fact(agent.state.diagnosis.evidence, "power_cable", "unknown", CLIENT, 3)
        assert evidence_drive(agent.state, agent.runtime, "nežinau") is not None  # revival
        set_fact(
            agent.state.diagnosis.evidence, "power_cable", "unknown", CLIENT, 4
        )  # still unreadable
        assert evidence_drive(agent.state, agent.runtime, "nežinau") is None  # hands over, no loop


class TestContradictionCorroboration:
    def test_uncorroborated_flip_dropped(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        # "Neturi kompiuterio" hallucinated device_present=nerado against a
        # settled "rado" — the keyword layer sees no such flip -> dropped.
        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(agent.state, agent.runtime, "Radau routerį prie lango")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(
                facts={"device_present": "not_found", "has_computer": "no"},
                understood="klientas neturi kompiuterio",
            ),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Neturi kompiuterio.")
        e = agent.state.diagnosis.evidence["device_present"]
        assert e["value"] == "found" and e["conflict"] is False  # phantom died
        assert agent.state.diagnosis.evidence["has_computer"]["value"] == "no"  # real fact landed

    def test_corroborated_flip_still_opens_conflict(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"lights": "on"}, understood="lemputė užsidegė"),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "O, dabar lemputė dega!")
        e = agent.state.diagnosis.evidence["lights"]
        assert e["conflict"] is True  # keywords agree -> the clarify machinery runs

    def test_flip_corroborated_by_key_own_markers(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        # Live 2026-08-11: ledger had power_cable=atjungtas (from "routeris
        # neturi maitinimo"); the caller then answered "Tai ikištas" WITHOUT
        # the topic word "laidas" — the general extractor saw no cable topic
        # and the TRUE update was dropped, so the hypothesis never confirmed
        # and the findings announce never fired. The key's OWN answer markers
        # (read_pending_answer) now corroborate the flip.
        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(
                facts={"power_cable": "unplugged"}, understood="routeris be maitinimo"
            ),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "routeris neturi maitinimo")
        assert agent.state.diagnosis.evidence["power_cable"]["value"] == "unplugged"
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"power_cable": "plugged"}, understood="laidas įkištas"),
        ):
            ingest_client_evidence(
                agent.state, agent.runtime, "Tai ikištas, viskas gerai"
            )  # STT dropped į
        e = agent.state.diagnosis.evidence["power_cable"]
        assert e["conflict"] is True  # accepted -> ONE clarify settles it


class TestTicketUnderstanding:
    """The ticket dialogue reads answers through the pass too (Andrius
    2026-08-10): "Bet kada galima per pietus iš ryto" IS an hours answer —
    the keyword list diverted it on "galima" and the hours defaulted."""

    def _ticket_agent(self, monkeypatch, stage="hours"):
        from agent.decide.rules.head import turn_head
        from agent.decide.rules.reply import scripted_words
        from agent.execute.ticket import begin_ticket_dialogue

        agent = _diagnosing_agent(monkeypatch)
        begin_ticket_dialogue(agent.state, agent.runtime, None)
        scripted_words(agent.state, agent.runtime, None)  # asks phone
        if stage == "hours":
            turn_head(
                agent.state, agent.runtime, "taip, tiks šis"
            )  # keyword consent (pass mocked off below)
            scripted_words(agent.state, agent.runtime, "taip, tiks šis")  # asks hours
        return agent

    def test_hours_with_galima_captured_not_diverted(self, db_connection, monkeypatch):
        from agent.decide.rules.head import turn_head

        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch(
            "agent.perceive.understand.understand_ticket",
            return_value={"value": "per pietus arba ryte", "type": "answer"},
        ):
            turn_head(agent.state, agent.runtime, "Bet kada galima per pietus iš ryto")
        assert agent.state.ticket.contact_hours == "per pietus arba ryte"
        assert agent.state.ticket.stage == "done"

    def test_phone_tas_pats_via_pass(self, db_connection, monkeypatch):
        from agent.decide.rules.head import turn_head

        agent = self._ticket_agent(monkeypatch, stage="phone")
        with patch(
            "agent.perceive.understand.understand_ticket",
            return_value={"value": "same_number", "type": "answer"},
        ):
            turn_head(agent.state, agent.runtime, "Stengiai tas, iš kurios kambinu")
        assert agent.state.ticket.contact_phone == "+37060012353"
        assert agent.state.ticket.stage == "hours"

    def test_real_question_still_diverts(self, db_connection, monkeypatch):
        from agent.decide.rules.head import turn_head

        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch(
            "agent.perceive.understand.understand_ticket",
            return_value={"value": None, "type": "question"},
        ):
            turn_head(agent.state, agent.runtime, "O kodėl turiu laukti skambučio?")
        assert agent.state.turn.ticket_offscript_question is True
        assert agent.state.ticket.contact_hours is None

    def test_pass_failure_falls_back_to_keywords(self, db_connection, monkeypatch):
        from agent.decide.rules.head import turn_head

        agent = self._ticket_agent(monkeypatch, stage="hours")
        with patch("agent.perceive.understand.understand_ticket", return_value=None):
            turn_head(agent.state, agent.runtime, "po 17 valandos")
        assert agent.state.ticket.contact_hours == "po 17 valandos"  # keyword plausibility path

    def test_stale_supratau_cleared_on_ticket_turns(self, db_connection, monkeypatch):
        from agent.graph_v2.state import GraphState
        from agent.perceive import perceive
        from agent.speak.context_card import context_card
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        agent = self._ticket_agent(monkeypatch, stage="hours")
        agent.state.turn.understanding = {"understood": "Routeris sugedęs", "type": "answer"}
        agent.state.turn.user_input = "bet kada"
        # The perceive node starts every turn with a clean read.
        perceive(agent.state, agent.runtime, "bet kada")
        with patch(
            "agent.perceive.understand.understand_ticket",
            return_value={"value": "bet kada", "type": "answer"},
        ):
            upd = run_turn_nodes(agent.state, Runtime(context=agent.runtime))
        state = GraphState(**upd)
        assert state.turn.understanding is None
        assert "Užregistravau" in state.turn.reply  # dialogue completed
        facts = context_card(state, agent.runtime) or ""
        assert "Routeris sugedęs" not in facts


class TestUnderstandWiring:
    def test_understanding_facts_land_on_ledger(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(facts={"device_present": "found"}, understood="klientas rado routerį")
        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(agent.state, agent.runtime, "Radau.")
        assert agent.state.diagnosis.evidence["device_present"]["value"] == "found"
        assert agent.state.turn.understanding["understood"] == "klientas rado routerį"

    def test_pass_failure_falls_back_to_keywords(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch("agent.perceive.understand.understand", return_value=None):
            ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        assert agent.state.diagnosis.evidence["lights"]["value"] == "off"  # keyword layer caught it

    def test_tipas_klausimas_routes_to_side_topic(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence
        from agent.perceive.side_topic import classify_side_topic

        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(turn_type="question", understood="klausia kainos")
        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(agent.state, agent.runtime, "O kiek man tai kainuos?")
        assert classify_side_topic(agent.state, agent.runtime, "O kiek man tai kainuos?") is True

    def test_tipas_nesupratimas_is_not_a_deviation_and_directs_reexplain(
        self, db_connection, monkeypatch
    ):
        from agent.perceive.evidence import ingest_client_evidence
        from agent.perceive.side_topic import classify_side_topic
        from agent.speak.context_card import context_card

        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(
            turn_type="confusion",
            understood="klientas neranda routerio",
            confusion="nežino, kuri dėžutė yra routeris",
        )
        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(
                agent.state, agent.runtime, "Nu nerandu aš čia nieko, kur ta dėžutė?"
            )
        assert (
            classify_side_topic(
                agent.state, agent.runtime, "Nu nerandu aš čia nieko, kur ta dėžutė?"
            )
            is False
        )
        facts = context_card(agent.state, agent.runtime)
        assert "NOT UNDERSTOOD BY THE CALLER" in facts and "kuri dėžutė" in facts
        assert "ACKNOWLEDGE" in facts

    def test_acknowledgement_directive_carries_supratau(self, db_connection, monkeypatch):
        from agent.perceive.evidence import ingest_client_evidence
        from agent.speak.context_card import context_card

        agent = _diagnosing_agent(monkeypatch)
        canned = _canned(facts={"lights": "off"}, understood="lemputės nedega")
        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(agent.state, agent.runtime, "ne daganiai viena")
        facts = context_card(agent.state, agent.runtime)
        assert "ACKNOWLEDGE" in facts and "lemputės nedega" in facts

    def test_contradiction_from_pass_flows_into_conflict_machinery(
        self, db_connection, monkeypatch
    ):
        from agent.perceive.evidence import ingest_client_evidence

        agent = _diagnosing_agent(monkeypatch)
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"has_computer": "no"}),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Neturiu kompiuterio")
        with patch(
            "agent.perceive.understand.understand",
            return_value=_canned(facts={"has_computer": "yes"}, turn_type="contradiction"),
        ):
            ingest_client_evidence(agent.state, agent.runtime, "Turiu kompiuterį")
        assert agent.state.diagnosis.contradiction is not None  # same clarify discipline as before

    def test_keyword_suite_untouched_without_flag(self, db_connection, monkeypatch):
        # CLASSIFIER=off (the whole deterministic suite) — the pass never runs.
        import os

        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setitem(os.environ, "CLASSIFIER", "off")
        agent = _diagnosing_agent(monkeypatch, understand_on=False)
        called = {"v": False}

        def _boom(*a, **k):
            called["v"] = True
            return None

        with patch("agent.perceive.understand.understand", side_effect=_boom):
            ingest_client_evidence(agent.state, agent.runtime, "Nedega nė viena lemputė")
        assert called["v"] is False
        assert agent.state.diagnosis.evidence["lights"]["value"] == "off"
