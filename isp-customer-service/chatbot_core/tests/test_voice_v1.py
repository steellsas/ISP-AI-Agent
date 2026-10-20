"""
VOICE_PLAN V1 — dynamic STT biasing + the too-short-audio guard + replay hooks.

The dialogue tells the ASR what to expect (last question + the pending fact's
answer vocabulary); sub-word audio fragments are dropped BEFORE Whisper can
hallucinate words from them; every asr trace event carries the context used,
so the replay bench can reproduce the live decoding exactly.
"""

from types import SimpleNamespace

from agent.background import apply_bg_diagnosis
from agent.delivery import apply_delivery
from agent.graph_v2.state import DiagnosisState, GraphState, IntakeState

from tests.engine_fakes import as_call


class TestComposePrompt:
    def test_joins_and_prefers_context_on_overflow(self):
        from src.adapters.asr.lt_text import compose_prompt

        assert compose_prompt("domenas", "kontekstas") == "domenas kontekstas"
        assert compose_prompt(None, "tik kontekstas") == "tik kontekstas"
        assert compose_prompt("d", None) == "d"
        long = compose_prompt("x" * 900, "SVARBUS KONTEKSTAS", max_len=100)
        assert long.endswith("SVARBUS KONTEKSTAS") and len(long) <= 100


class TestEchoOverlap:
    """Our own words heard back are told by a fuzzy token overlap (barge-in echo)."""

    def test_fuzzy_overlap_tolerates_garbled_endings(self):
        from agent.barge_in import token_overlap

        assert token_overlap("dega lempute routero", "ar dega lemputės ant routerio?") >= 0.8
        assert token_overlap("visai kita tema", "ar dega lemputės?") < 0.5


class TestPerceptionModelKnob:
    """Tempo wave: the perception family may run on a faster (Groq) model —
    PERCEPTION_MODEL overrides; 'default'/empty falls back to the agent model."""

    def test_override_and_fallback(self, monkeypatch):
        from agent.perceive.understand import perception_model

        monkeypatch.delenv("PERCEPTION_MODEL", raising=False)
        assert perception_model("gpt-4o-mini") == "gpt-4o-mini"
        monkeypatch.setenv("PERCEPTION_MODEL", "default")
        assert perception_model("gpt-4o-mini") == "gpt-4o-mini"
        monkeypatch.setenv("PERCEPTION_MODEL", "groq/openai/gpt-oss-120b")
        assert perception_model("gpt-4o-mini") == "groq/openai/gpt-oss-120b"

    def test_understand_call_uses_the_override(self, monkeypatch):
        from agent.perceive import understand
        from src.services.llm import client as llm_client

        seen = {}

        def fake(messages=None, model=None, **k):
            seen["model"] = model
            return {"type": "answer", "facts": {}, "confidence": 0.9}

        monkeypatch.setattr(llm_client, "llm_json_completion", fake)
        monkeypatch.setenv("PERCEPTION_MODEL", "groq/openai/gpt-oss-120b")
        u = understand.understand(
            "nedega", anchor="Ar dega?", needs="", ledger_summary="", model="gpt-4o-mini"
        )
        assert u is not None and seen["model"] == "groq/openai/gpt-oss-120b"

    def test_groq_provider_resolution(self):
        from src.services.llm.client import _get_provider, get_model_info

        assert _get_provider("groq/openai/gpt-oss-120b") == "groq"
        assert get_model_info("groq/qwen/qwen3.6-27b")["supports_json_mode"] is True


class TestCheckin:
    """G3: the silence check-in fires only while a question stands mid-call."""

    def test_awaiting_caller_gate(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown")
        a = session
        a.state.dialog.last_question = ""
        assert session.awaiting_caller() is False
        a.state.dialog.last_question = "Ar dega lemputė?"
        assert session.awaiting_caller() is True
        a.state.closing.case_closed = True
        assert session.awaiting_caller() is False

    def test_checkin_phrase_and_confusion_markers(self):
        from agent.contract.locale import phrase
        from agent.perceive.detectors import INTENT_CONFUSED, detect_turn_intent

        assert "sekasi" in phrase("identification.checkin")
        # G1: a struggling caller gets the explain-simpler path…
        assert detect_turn_intent("Man neišeina to padaryti") == INTENT_CONFUSED
        assert detect_turn_intent("Nežinau kaip ten žiūrėti") == INTENT_CONFUSED
        # …but the step ROUTING answer stays an answer, never confusion.
        assert detect_turn_intent("Nepavyko, interneto nėra") != INTENT_CONFUSED


class TestSessionAsrContext:
    def test_builds_from_the_question(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown")
        a = session
        a.state.dialog.last_question = "Ar dega bent viena lemputė?"
        a.state.diagnosis.pending_evidence_key = "lights"
        ctx = session.asr_context()
        assert ctx and "lemputė" in ctx

    def test_no_question_no_context(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown")
        session.state.dialog.last_question = ""
        assert session.asr_context() is None


class TestTtsCache:
    def test_tts_cache_short_circuits(self, monkeypatch):
        from src.adapters.tts.edge_tts import EdgeTTSProvider

        monkeypatch.delenv("TTS_RATE", raising=False)
        monkeypatch.delenv("TTS_PITCH", raising=False)
        p = EdgeTTSProvider()
        EdgeTTSProvider._CACHE[("Labas.", "lt-LT-LeonasNeural", None, None)] = b"HIT"
        assert p._synthesize_one("Labas.", "lt-LT-LeonasNeural") == b"HIT"


class TestBgDiagnosisGate:
    """S2 gate: the background read is a REFRESH — never applied in the
    solution/bridge phase."""

    def _agent(self, events):
        from types import SimpleNamespace

        from tests.calls import make_agent

        agent = make_agent(
            "unknown", tracer=SimpleNamespace(emit=lambda k, **f: events.append((k, f)))
        )
        agent.state.identity.customer_id = "CUST009"
        return agent

    def test_same_verdict_applies(self, db_connection):
        import json as _json

        events = []
        agent = self._agent(events)
        agent.state.turn.bg_diagnosis = _json.dumps(
            {"success": True, "verdict": {"reason": "no_mac_observed"}}
        )
        apply_bg_diagnosis(agent.state, agent.runtime)
        assert any(f.get("action") == "applied" for _k, f in events)

    def test_bridge_phase_always_discards(self, db_connection):
        import json as _json

        events = []
        agent = self._agent(events)
        agent.state.resolution.bridge_bound = True
        agent.state.turn.bg_diagnosis = _json.dumps(
            {"success": True, "verdict": {"reason": "no_mac_observed"}}
        )
        apply_bg_diagnosis(agent.state, agent.runtime)
        assert any(f.get("action") == "discarded" for _k, f in events)


class TestDeliveryLedger:
    """D1 — the engine's history keeps only what the caller actually HEARD
    after a barge-in; the unheard tail resurfaces once via the narrator."""

    def test_apply_delivery_truncates_history_and_surfaces_tail(self, db_connection):
        from agent.speak.context_card import context_card

        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.messages.append({"role": "user", "content": "neveikia"})
        agent.state.messages.append({"role": "assistant", "content": "Pirmas. Antras. Trečias."})
        apply_delivery(agent.state, agent.runtime, ["Pirmas.", "Antras.", "Trečias."], 1)
        assert agent.state.messages[-1]["content"] == "Pirmas. —"
        assert agent.state.voice.undelivered_tail == "Antras. Trečias."
        block = context_card(agent.state, agent.runtime) or ""
        assert "NOT HEARD" in block and "Antras." in block
        # consumed once — the note must not nag every later turn
        assert agent.state.voice.undelivered_tail is None
        assert "NOT HEARD" not in (context_card(agent.state, agent.runtime) or "")

    def test_apply_delivery_nothing_heard(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.messages.append({"role": "assistant", "content": "Visas tekstas."})
        apply_delivery(agent.state, agent.runtime, ["Visas tekstas."], 0)
        assert agent.state.messages[-1]["content"] == "—"
        assert agent.state.voice.undelivered_tail == "Visas tekstas."

    def test_apply_delivery_all_heard_is_noop(self, db_connection):
        from tests.calls import make_agent

        agent = make_agent("unknown")
        agent.state.messages.append({"role": "assistant", "content": "Viskas. Gerai."})
        apply_delivery(agent.state, agent.runtime, ["Viskas.", "Gerai."], 2)
        assert agent.state.messages[-1]["content"] == "Viskas. Gerai."
        assert agent.state.voice.undelivered_tail is None
