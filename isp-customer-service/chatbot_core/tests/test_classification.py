"""
Klasifikacijos kaskada ir kompetencijų politika (DIALOGO_ETALONAS diskusija,
2026-09-02): L1 trigger'iai + L2 LLM iš failo katalogo, politikos
(sprendzia / nelieciam / pokalbis), patvirtinimo laiptai, vartų kopėčios ir
„neaiškaus gedimo" tiketo tipas.
"""

from types import SimpleNamespace


def _agent():
    from agent.react_agent import ReactAgent

    return ReactAgent(caller_phone="unknown")


class TestCatalog:
    def test_politika_declared_and_default(self):
        from agent.faults import problem_politika

        assert problem_politika("internet_down") == "sprendzia"
        assert problem_politika("tv") == "sprendzia"
        assert problem_politika("saskaitos") == "nelieciam"
        assert problem_politika("pokalbis") == "pokalbis"
        assert problem_politika("nezinomas_tipas") == "sprendzia"  # default
        assert problem_politika(None) == "sprendzia"

    def test_catalog_options_built_from_descriptions(self):
        from agent.faults import problem_catalog_options

        opts = problem_catalog_options()
        assert "internet_down" in opts and "nekrauna" in opts["internet_down"]
        assert "saskaitos" in opts and "pokalbis" in opts

    def test_boundary_phrases_exist(self):
        from agent.faults import problem_atsakymas, problem_patvirtinimas

        assert "techninės pagalbos" in problem_atsakymas("saskaitos")
        assert "internet" in problem_atsakymas("pokalbis")
        assert "?" in problem_patvirtinimas("internet_down")

    def test_l1_still_classifies_solvable_types(self):
        from agent.nlu import classify_problem

        assert classify_problem("neveikia internetas") == "internet_down"
        assert classify_problem("baisiai lėtas internetas") == "internet_slow"
        assert classify_problem("skambinu dėl sąskaitos") == "saskaitos"

    def test_negated_problem_is_not_a_problem(self):
        """Live G2 (2026-09-02): 'interneto bėdų NETURIU, tik dėl sąskaitos'
        committed internet_down via the bare trigger."""
        from agent.nlu import classify_problem

        assert classify_problem("Ne, interneto bėdų neturiu, tik dėl sąskaitos") is None
        assert classify_problem("internetas veikia, bėdų nėra") is None


class TestPolitikaIngest:
    """nelieciam/pokalbis tipai NIEKADA netampa problem_type — vartai atsako
    riba, identifikacija neprasideda."""

    def test_saskaitos_never_sets_problem_type(self, db_connection):
        agent = _agent()
        agent._prefill_slots_from_text("Kodėl man tokia didelė sąskaita?")
        assert agent.state.problem_type is None
        assert agent._boundary_problem == "saskaitos"

    def test_boundary_reply_states_competence(self, db_connection):
        agent = _agent()
        agent._prefill_slots_from_text("Kodėl man tokia didelė sąskaita?")
        reply = agent._identification_scripted_reply("Kodėl man tokia didelė sąskaita?")
        assert reply and "techninės pagalbos" in reply
        assert agent.state.problem_type is None and not agent.state.case_closed

    def test_solvable_problem_still_flows(self, db_connection):
        agent = _agent()
        agent._prefill_slots_from_text("Labas, neveikia internetas")
        assert agent.state.problem_type == "internet_down"


class TestGateGuessConfirm:
    """Patvirtinimo laiptai: „Ar gerai suprantu — …?" → „taip" komituoja ir
    pokalbis TĘSIASI tą patį turn'ą (vartai nebaigia pokalbio, kuris juda)."""

    def test_yes_commits_and_falls_through(self, db_connection):
        agent = _agent()
        agent._problem_guess = "internet_down"
        reply = agent._identification_scripted_reply("Taip, būtent")
        assert agent.state.problem_type == "internet_down"
        assert not agent.state.case_closed
        # fall-through reached the intake ladder (anamnesis asked this turn)
        assert agent.state.anamnesis_asked or reply is not None

    def test_no_keeps_gate_open(self, db_connection):
        agent = _agent()
        agent._problem_guess = "internet_down"
        agent._identification_scripted_reply("Ne, ne dėl to skambinu")
        assert agent.state.problem_type is None
        assert not agent.state.case_closed
        assert agent._problem_guess is None  # spėjimas nunaudotas, kopėčios tęsiasi


class TestGateL2:
    """L2 LLM spėjimas iš konteksto (klasifikatorius mock'intas)."""

    def _gate(self, agent, text):
        return agent._identification_scripted_reply(text)

    def test_high_confidence_commits_implicitly(self, db_connection, monkeypatch):
        from agent import nlu

        monkeypatch.setenv("CLASSIFIER", "on")
        monkeypatch.setattr(
            nlu, "classify_problem_llm", lambda t, model=None: ("internet_down", 0.9)
        )
        agent = _agent()
        self._gate(agent, "Niekas man nekrauna nuo pat ryto")
        assert agent.state.problem_type == "internet_down"
        assert not agent.state.case_closed

    def test_medium_confidence_asks_confirmation(self, db_connection, monkeypatch):
        from agent import nlu

        monkeypatch.setenv("CLASSIFIER", "on")
        monkeypatch.setattr(
            nlu, "classify_problem_llm", lambda t, model=None: ("internet_down", 0.6)
        )
        agent = _agent()
        reply = self._gate(agent, "Kažkas namuose nebeveikia gerai")
        assert agent.state.problem_type is None
        assert agent._problem_guess == "internet_down"
        assert reply and "Ar gerai suprantu" in reply

    def test_boundary_type_from_context(self, db_connection, monkeypatch):
        from agent import nlu

        monkeypatch.setenv("CLASSIFIER", "on")
        monkeypatch.setattr(
            nlu, "classify_problem_llm", lambda t, model=None: ("kita_ne_musu", 0.8)
        )
        agent = _agent()
        reply = self._gate(agent, "Man šiukšlių neišveža jau savaitę")
        assert agent.state.problem_type is None
        assert reply and "nepadėsiu" in reply
        assert not agent.state.case_closed

    def test_unclear_falls_to_ladder(self, db_connection, monkeypatch):
        from agent import nlu

        monkeypatch.setenv("CLASSIFIER", "on")
        monkeypatch.setattr(nlu, "classify_problem_llm", lambda t, model=None: (None, 0.0))
        agent = _agent()
        reply = self._gate(agent, "Mendulija kadulija")
        assert agent.state.problem_type is None
        assert reply is not None or agent._ident_directive is not None


class TestAccumulatedContext:
    """Sukaupto konteksto principas (Andrius 2026-09-02: „kai informacija
    pasipildo, ateina supratimas") — VAD sukarpyta mintis klasifikuojama iš
    replikų uodegos, ne vienos frazės."""

    def test_l2_reads_the_joined_tail(self, db_connection, monkeypatch):
        from agent import nlu

        got: list = []

        def _fake(text, model=None):
            got.append(text)
            return ("internet_down", 0.9)

        monkeypatch.setenv("CLASSIFIER", "on")
        monkeypatch.setattr(nlu, "classify_problem_llm", _fake)
        agent = _agent()
        agent.state.heard_utterances.extend(["Labai diena.", "Ora šiandien kažkoks netoks."])
        agent.state.heard_utterances.append("gal dėl to neturiu interneto?")
        agent._identification_scripted_reply("gal dėl to neturiu interneto?")
        assert got and "netoks" in got[0] and "neturiu interneto" in got[0]
        assert agent.state.problem_type == "internet_down"

    def test_story_window_while_problem_unknown(self, db_connection):
        from agent.endpoint import classify_endpoint, story_ms

        agent = _agent()
        # užbaigtas sakinys, bet problema dar nežinoma -> laukiam ilgiau
        assert classify_endpoint(agent, "Oras šiandien kažkoks netoks.") == (
            "slow",
            story_ms(),
        )
        # atsisveikinimas kerpamas greitai net ir vartuose
        assert classify_endpoint(agent, "Ačiū, viso gero")[0] == "fast"
        # problema jau žinoma -> normalus langas
        agent.state.problem_type = "internet_down"
        assert classify_endpoint(agent, "Oras šiandien kažkoks netoks.") == ("normal", None)

    def test_final_flush_hands_open_segment_to_engine(self, db_connection, monkeypatch):
        from app.main import _final_flush

        monkeypatch.setenv("FINAL_FLUSH", "on")
        got: list = []
        front = SimpleNamespace(export_open=lambda: b"\x01\x02" * 20_000, _rate=16_000)
        ms = SimpleNamespace(
            front=front,
            overlay_front=None,
            voice=SimpleNamespace(transcribe_partial=lambda wav: "gal dėl to neturiu interneto"),
            session=SimpleNamespace(
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
                apply_overlay=lambda texts: got.append(texts),
            ),
        )
        _final_flush(ms)
        assert got == [["gal dėl to neturiu interneto"]]

    def test_final_flush_skips_noise_and_empty(self, db_connection, monkeypatch):
        from app.main import _final_flush

        monkeypatch.setenv("FINAL_FLUSH", "on")
        got: list = []
        ms = SimpleNamespace(
            front=SimpleNamespace(export_open=lambda: b"\x01" * 100, _rate=16_000),
            overlay_front=SimpleNamespace(export_open=lambda: None, _rate=16_000),
            voice=SimpleNamespace(transcribe_partial=lambda wav: "kažkas"),
            session=SimpleNamespace(
                tracer=SimpleNamespace(emit=lambda *a, **k: None),
                apply_overlay=lambda texts: got.append(texts),
            ),
        )
        _final_flush(ms)
        assert got == []


class TestPendingFallback:
    """2026-09-03 (eval S6 flake): the pack's first question may go out from
    the STEP HINT before the drive's ask bookkeeping — with no pending key the
    deterministic answer read was skipped and the fact lived or died on the
    LLM pass. Now the NEXT MISSING evidence key stands in; its conservative
    marks still must hit."""

    def test_answer_lands_without_pending_key(self, db_connection, monkeypatch):
        from types import SimpleNamespace as NS
        from unittest.mock import patch

        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020112")
        agent.state.customer_id = "CUST112"
        agent.state.problem_type = "internet_down"
        agent.state.resolution = {"verdict": "router_hung", "step": "rh_scope"}
        assert getattr(agent, "_evidence_last_ask_key", None) is None  # no ask yet
        canned = NS(
            tipas="atsakymas",
            faktai={},
            supratau="x",
            pasitikejimas=1.0,
            atsakymo_kokybe="pilnas",
        )
        with patch("agent.understand.understand", return_value=canned):
            agent._ingest_client_evidence("Visuose įrenginiuose")
        assert agent.state.evidence["fail_scope"]["value"] == "visuose"

    def test_unrelated_utterance_commits_nothing(self, db_connection):
        from unittest.mock import patch

        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="+37060020112")
        agent.state.customer_id = "CUST112"
        agent.state.problem_type = "internet_down"
        agent.state.resolution = {"verdict": "router_hung", "step": "rh_scope"}
        with patch("agent.understand.understand", return_value=None):
            agent._ingest_client_evidence("O kiek visa tai kainuos?")
        assert agent.state.evidence.get("fail_scope") is None


class TestUnclearFaultTicket:
    def test_ticket_need_without_verdict_is_honest(self, db_connection):
        from agent.ticket_flow import ticket_need

        agent = _agent()
        agent.state.problem_type = "tv"
        assert "neaiškus" in ticket_need(agent)

    def test_ticket_need_with_verdict_unchanged(self, db_connection):
        from agent.ticket_flow import ticket_need

        agent = _agent()
        agent.state.resolution = {"verdict": "no_mac_observed"}
        assert "maršrutizatorius" in ticket_need(agent)


class TestCompetenceSurface:
    def test_greeting_discloses_ai_and_scope(self, db_connection):
        from agent.config import AgentConfig

        g = AgentConfig().greeting_message
        assert "dirbtinio intelekto" in g
        assert "televizijos" in g


class TestNoPathTicket:
    """Kelio-nėra taisyklė (Andrius 2026-09-03): in-scope problema +
    identifikuotas klientas + nėra pack'o → sąžiningas „neaiškaus gedimo"
    tiketas, ne svetimo domeno improvizacija (gyvai: TV skambutis buvo
    vedamas per interneto WiFi klausimus)."""

    def test_problem_has_path(self):
        from agent.faults import problem_has_path

        assert problem_has_path("internet_down") is True
        assert problem_has_path("tv") is False
        assert problem_has_path("internet_slow") is False
        assert problem_has_path(None) is False

    def test_tv_goes_to_unclear_ticket_not_internet_pack(self, db_connection):
        agent = _agent()
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "tv"
        assert agent.ensure_diagnosed() is True
        r = agent.state.resolution
        assert r["verdict"] == "unclear_fault" and r["step"] == "escalate"
        assert agent._ticket_stage == "phone"  # dialogue began deterministically
        from agent.ticket_flow import ticket_need

        assert "neaiškus" in ticket_need(agent)

    def test_internet_down_still_diagnoses(self, db_connection):
        agent = _agent()
        agent.state.customer_id = "CUST009"
        agent.state.problem_type = "internet_down"
        agent.ensure_diagnosed()
        assert (agent.state.resolution or {}).get("verdict") != "unclear_fault"


class TestGateMaxTurns:
    def test_knob_controls_the_close(self, db_connection, monkeypatch):
        monkeypatch.setenv("GATE_MAX_TURNS", "2")
        monkeypatch.setenv("NARRATOR_QUESTIONS", "off")
        agent = _agent()
        r1 = agent._identification_scripted_reply("Mendulija kadulija")
        assert not agent.state.case_closed and r1
        r2 = agent._identification_scripted_reply("Kadulija mendulija")
        assert agent.state.case_closed and "skambinkite" in r2
        assert agent.state.ticket_id is None  # no customer -> no ticket, ever


class TestRepeatedTokenNoise:
    def test_whisper_loop_is_noise(self):
        from src.adapters.asr.lt_text import is_asr_noise

        assert is_asr_noise("Žemės gatvės gatvės gatvės") is True
        assert is_asr_noise("Žemės gatvės gatvės gatvės interneto lizdą.") is True

    def test_real_speech_is_not(self):
        from src.adapters.asr.lt_text import is_asr_noise

        assert is_asr_noise("Ne ne ne, palaukit!") is False  # short refusal exempt
        assert is_asr_noise("Labai labai gerai") is False  # only 2 in a row
        assert is_asr_noise("Radau routerį prie lango") is False
