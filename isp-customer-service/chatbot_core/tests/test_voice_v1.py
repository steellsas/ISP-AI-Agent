"""
VOICE_PLAN V1 — dynamic STT biasing + the too-short-audio guard + replay hooks.

The dialogue tells the ASR what to expect (last question + the pending fact's
answer vocabulary); sub-word audio fragments are dropped BEFORE Whisper can
hallucinate words from them; every asr trace event carries the context used,
so the replay bench can reproduce the live decoding exactly.
"""

from types import SimpleNamespace

from agent.voice_pipeline import VoicePipeline, audio_duration_s


class _Recorder:
    def __init__(self):
        self.events = []

    def emit(self, kind, **fields):
        self.events.append((kind, fields))


class _StubTTS:
    def synthesize(self, text, language=None):
        return b"AUDIO"


def _session(context=None):
    s = SimpleNamespace(
        config=SimpleNamespace(language="lt"),
        is_complete=False,
        tracer=_Recorder(),
        handle_turn=lambda text: f"atsakymas į: {text}",
    )
    if context is not None:
        s.asr_context = lambda: context
    return s


class TestComposePrompt:
    def test_joins_and_prefers_context_on_overflow(self):
        from src.adapters.asr.lt_text import compose_prompt

        assert compose_prompt("domenas", "kontekstas") == "domenas kontekstas"
        assert compose_prompt(None, "tik kontekstas") == "tik kontekstas"
        assert compose_prompt("d", None) == "d"
        long = compose_prompt("x" * 900, "SVARBUS KONTEKSTAS", max_len=100)
        assert long.endswith("SVARBUS KONTEKSTAS") and len(long) <= 100


class TestTooShortGuard:
    def test_sub_word_fragment_is_dropped_before_asr(self, monkeypatch):
        monkeypatch.setenv("ASR_MIN_AUDIO_S", "0.3")
        calls = []
        asr = SimpleNamespace(transcribe=lambda *a, **k: calls.append(1) or "žodis")
        pipeline = VoicePipeline(_session(), asr, _StubTTS())
        # 0.1 s of 16 kHz mono int16 = 3200 bytes
        turn = pipeline.handle_audio(b"\x00" * 3200, sample_rate=16_000)
        assert calls == [] and turn.reply_text == "" and turn.reply_audio == b""
        kinds = [k for k, f in pipeline.session.tracer.events]
        assert "asr" in kinds
        _, fields = pipeline.session.tracer.events[0]
        assert fields["dropped"] is True and fields["reason"] == "too_short"

    def test_normal_audio_passes(self):
        asr = SimpleNamespace(transcribe=lambda audio, **k: "labas")
        pipeline = VoicePipeline(_session(), asr, _StubTTS())
        turn = pipeline.handle_audio(b"\x00" * 32_000, sample_rate=16_000)  # 1 s
        assert turn.transcript == "labas" and turn.reply_text

    def test_duration_reads_raw_pcm(self):
        assert audio_duration_s(b"\x00" * 32_000, 16_000) == 1.0
        assert audio_duration_s(b"", 16_000) == 0.0


class TestDynamicContext:
    def test_context_reaches_the_asr_and_the_trace(self):
        seen = {}

        def transcribe(audio, *, language=None, sample_rate=16_000, context=None):
            seen["context"] = context
            return "nedega"

        pipeline = VoicePipeline(
            _session(context="Klausimas: Ar dega lemputė? Galimi atsakymai: dega, nedega."),
            SimpleNamespace(transcribe=transcribe),
            _StubTTS(),
        )
        turn = pipeline.handle_audio(b"\x00" * 32_000, sample_rate=16_000)
        assert "nedega" in seen["context"] and turn.transcript == "nedega"
        asr_events = [f for k, f in pipeline.session.tracer.events if k == "asr"]
        assert "nedega" in asr_events[0]["context"]

    def test_legacy_asr_without_context_param_keeps_working(self):
        def transcribe(audio, *, language=None, sample_rate=16_000):  # no context
            return "senas adapteris"

        pipeline = VoicePipeline(
            _session(context="bet koks"), SimpleNamespace(transcribe=transcribe), _StubTTS()
        )
        turn = pipeline.handle_audio(b"\x00" * 32_000, sample_rate=16_000)
        assert turn.transcript == "senas adapteris"


class TestSmartBargeIn:
    """L3a: what an interruption MEANS — default-deny, negation always stops,
    backchannels/echo never derail the dialogue."""

    def test_consent_stop_echo_substantive(self):
        from agent.barge_in import classify_interruption

        said = "Pažiūrėkite, ar ant routerio dega bent viena lemputė."
        assert classify_interruption("Taip taip", said) == "consent"
        assert classify_interruption("Gerai, mhm", said) == "consent"
        assert classify_interruption("Ne, palaukit!", said) == "stop"
        assert classify_interruption("Ne", said) == "stop"
        # speakerphone echo: our own words, garbled endings
        assert classify_interruption("ar ant routero dega lempute", said) == "echo"
        # real content — even short — processes normally
        assert classify_interruption("Lemputės nedega", said) == "substantive"
        assert classify_interruption("Nu... nežinau", said) == "substantive"
        assert classify_interruption("", said) == "substantive"

    def test_fuzzy_overlap_tolerates_garbled_endings(self):
        from agent.barge_in import token_overlap

        assert token_overlap("dega lempute routero", "ar dega lemputės ant routerio?") >= 0.8
        assert token_overlap("visai kita tema", "ar dega lemputės?") < 0.5

    def test_stream_turn_consent_reanchors_instead_of_derailing(self):
        turns = []

        def transcribe(audio, **k):
            return "Taip taip"

        session = _session()
        session.anchor_text = lambda: "Ar dega bent viena lemputė?"
        session.handle_turn = lambda text: turns.append(text) or "NETURI BŪTI"
        session.handle_turn_stream = None  # force the non-stream agent path
        pipeline = VoicePipeline(session, SimpleNamespace(transcribe=transcribe), _StubTTS())
        chunks = list(
            pipeline.stream_turn(
                b"\x00" * 32_000,
                interruption=lambda t: "consent",
            )
        )
        assert turns == []  # the engine never saw the backchannel
        assert chunks == [b"AUDIO"]  # the standing question was re-spoken
        events = dict(session.tracer.events)
        assert events.get("barge_in", {}).get("verdict") == "consent"

    def test_stream_turn_substantive_processes_normally(self):
        session = _session()
        session.handle_turn_stream = None
        seen = []
        session.handle_turn = lambda text: seen.append(text) or "atsakau"
        pipeline = VoicePipeline(
            session, SimpleNamespace(transcribe=lambda a, **k: "nedega lemputės"), _StubTTS()
        )
        chunks = list(pipeline.stream_turn(b"\x00" * 32_000, interruption=lambda t: "substantive"))
        assert seen == ["nedega lemputės"] and chunks


class TestPerceptionModelKnob:
    """Tempo wave: the perception family may run on a faster (Groq) model —
    PERCEPTION_MODEL overrides; 'default'/empty falls back to the agent model."""

    def test_override_and_fallback(self, monkeypatch):
        from agent.understand import perception_model

        monkeypatch.delenv("PERCEPTION_MODEL", raising=False)
        assert perception_model("gpt-4o-mini") == "gpt-4o-mini"
        monkeypatch.setenv("PERCEPTION_MODEL", "default")
        assert perception_model("gpt-4o-mini") == "gpt-4o-mini"
        monkeypatch.setenv("PERCEPTION_MODEL", "groq/openai/gpt-oss-120b")
        assert perception_model("gpt-4o-mini") == "groq/openai/gpt-oss-120b"

    def test_understand_call_uses_the_override(self, monkeypatch):
        from agent import understand
        from src.services.llm import client as llm_client

        seen = {}

        def fake(messages=None, model=None, **k):
            seen["model"] = model
            return {"tipas": "atsakymas", "faktai": {}, "pasitikejimas": 0.9}

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
        a = session._agent
        a.state.last_question = ""
        assert session.awaiting_caller() is False
        a.state.last_question = "Ar dega lemputė?"
        assert session.awaiting_caller() is True
        a.state.case_closed = True
        assert session.awaiting_caller() is False

    def test_checkin_phrase_and_confusion_markers(self):
        from agent.identification import phrase
        from agent.resolution import INTENT_CONFUSED, detect_turn_intent

        assert "sekasi" in phrase("checkin")
        # G1: a struggling caller gets the explain-simpler path…
        assert detect_turn_intent("Man neišeina to padaryti") == INTENT_CONFUSED
        assert detect_turn_intent("Nežinau kaip ten žiūrėti") == INTENT_CONFUSED
        # …but the step ROUTING answer stays an answer, never confusion.
        assert detect_turn_intent("Nepavyko, interneto nėra") != INTENT_CONFUSED


class TestSessionAsrContext:
    def test_builds_from_question_and_pending_vocabulary(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown")
        a = session._agent
        a.state.last_question = "Ar dega bent viena lemputė?"
        a.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights"}
        a._evidence_last_ask_key = "lights"
        ctx = session.asr_context()
        assert ctx and "lemputė" in ctx
        assert "nedega" in ctx and "dega" in ctx  # the pack's atsakymai markers

    def test_no_question_no_context(self, db_connection):
        from agent.session import AgentSession

        session = AgentSession(caller_phone="unknown")
        session._agent.state.last_question = ""
        assert session.asr_context() is None


class TestSpeculation:
    """S1 (2026-08-24): branches prepared while the caller answers; served only
    on an exact, fact-clean match — any doubt falls to the normal path."""

    def _agent(self, db_connection=None):
        from agent.react_agent import ReactAgent

        agent = ReactAgent(caller_phone="unknown")
        agent.state.customer_id = "CUST009"
        agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_lights"}
        from agent.evidence import CLIENT, set_fact

        set_fact(agent.state.evidence, "device_present", "rado", CLIENT, 1)
        agent._evidence_last_ask_key = "lights"
        return agent

    def test_plan_branches_from_the_ledger(self, db_connection):
        from agent.speculation import plan_branches

        plan = plan_branches(self._agent())
        assert plan and plan["pending_key"] == "lights"
        assert plan["branches"]["nedega"]["kind"] == "evidence"
        assert plan["branches"]["nedega"]["key"] == "power_cable"
        assert "dega" not in plan["branches"]  # refuted -> pivot path, not speculated

    def test_match_gates_are_conservative(self, db_connection):
        from agent.speculation import match

        agent = self._agent()
        base = {
            "pending_key": "lights",
            "verdict": "no_mac_observed",
            "branches": {"nedega": {"kind": "evidence", "key": "power_cable", "text": "x?"}},
        }
        agent._spec_cache = dict(base)
        assert match(agent, "O kiek tai kainuos?") is None  # question
        agent._spec_cache = dict(base)
        assert match(agent, "Nedega, bet keičiau routerį vakar") is None  # extra fact
        agent._spec_cache = dict(base)
        hit = match(agent, "Nedega nė viena")
        assert hit and hit["key"] == "power_cable"
        assert agent._spec_cache is None  # one shot

    def test_injection_consumed_only_on_directive_match(self, db_connection):
        agent = self._agent()
        agent._injected_reply = {
            "kind": "evidence",
            "key": "power_cable",
            "text": "Ar laidas įkištas?",
        }
        agent._evidence_directive = {
            "key": "power_cable",
            "reikia": "x",
            "kodel": "",
            "klausimas": "",
        }
        assert agent._consume_injected_reply() == "Ar laidas įkištas?"
        agent._injected_reply = {"kind": "evidence", "key": "outlet_works", "text": "Ne tas?"}
        assert agent._consume_injected_reply() is None  # directive key mismatch

    def test_pipeline_serves_cached_audio_on_hit(self):
        from types import SimpleNamespace

        from agent.voice_pipeline import VoicePipeline

        session = SimpleNamespace(
            config=SimpleNamespace(language="lt"),
            is_complete=False,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
            speculation_match=lambda t: b"CACHED",
            _last_injected_text="Ar laidas įkištas?",
            handle_turn=lambda t: "Ar laidas įkištas?",
        )
        pipeline = VoicePipeline(
            session, SimpleNamespace(transcribe=lambda a, **k: "nedega"), _StubTTS()
        )
        chunks = list(pipeline.stream_turn(b"\x00" * 32_000))
        assert chunks == [b"CACHED"]

    def test_tts_cache_short_circuits(self, monkeypatch):
        from src.adapters.tts.edge_tts import EdgeTTSProvider

        monkeypatch.delenv("TTS_RATE", raising=False)
        monkeypatch.delenv("TTS_PITCH", raising=False)
        p = EdgeTTSProvider()
        EdgeTTSProvider._CACHE[("Labas.", "lt-LT-LeonasNeural", None, None)] = b"HIT"
        assert p._synthesize_one("Labas.", "lt-LT-LeonasNeural") == b"HIT"
