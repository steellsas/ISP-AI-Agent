"""
Tests for the Phase 3 voice adapters and the VoicePipeline glue.

These run offline: the engine imports (faster-whisper, gTTS) are lazy, so the
adapters construct without the optional `voice` dependency and we exercise
Protocol conformance, empty-input behavior, WAV decoding, and the
ASR -> AgentSession -> TTS orchestration with fakes. Tests that need the real
engines/network are guarded with importorskip.
"""

import io
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from adapters.asr import FasterWhisperASR, GroqWhisperASR
from adapters.tts import GTTSProvider
from agent.voice_pipeline import VoicePipeline, VoiceTurn
from ports.asr import ASRProvider
from ports.tts import TTSProvider


def _make_wav(samples: np.ndarray, rate: int) -> bytes:
    """Encode mono int16 samples as a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


# --- Fakes for the pipeline orchestration test ----------------------------


class _FakeASR:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, *, language=None, sample_rate=16_000):
        self.calls.append((audio, language, sample_rate))
        return "neveikia internetas"


class _FakeTTS:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, *, language=None):
        self.calls.append((text, language))
        return b"AUDIO:" + text.encode("utf-8")


class _FakeConfig:
    language = "lt"


class _FakeSession:
    def __init__(self):
        self.config = _FakeConfig()
        self.is_complete = False
        self.turns = []

    def greeting(self):
        return "Labas!"

    def handle_turn(self, text):
        self.turns.append(text)
        return f"atsakymas: {text}"


class _FakeStreamingTTS:
    """A TTSProvider that also streams: one chunk per sentence."""

    def synthesize(self, text, *, language=None):
        return b"A:" + text.encode()

    def stream(self, text, *, language=None):
        from adapters.tts import split_sentences

        for sentence in split_sentences(text):
            yield b"A:" + sentence.encode()


class _FakeStreamingSession(_FakeSession):
    """A session that STREAMS the reply token by token (Pillar C3)."""

    def handle_turn_stream(self, text):
        yield from ("Svei", "ki. ", "Ar ", "veikia?")


class TestProtocolConformance:
    """Adapters and fakes must satisfy their port Protocols (structural)."""

    def test_faster_whisper_is_asr_provider(self):
        assert isinstance(FasterWhisperASR(), ASRProvider)

    def test_gtts_is_tts_provider(self):
        assert isinstance(GTTSProvider(), TTSProvider)

    def test_groq_is_asr_provider(self):
        # Construct without a key (no client built until transcribe).
        assert isinstance(GroqWhisperASR(api_key="x"), ASRProvider)

    def test_fakes_satisfy_protocols(self):
        assert isinstance(_FakeASR(), ASRProvider)
        assert isinstance(_FakeTTS(), TTSProvider)


class TestEmptyInputs:
    """Empty edges should short-circuit before any engine/network use."""

    def test_tts_empty_text_returns_empty_bytes(self):
        tts = GTTSProvider()
        assert tts.synthesize("") == b""
        assert tts.synthesize("   ") == b""

    def test_asr_empty_audio_returns_empty_string(self):
        # No model load happens: zero samples returns before _ensure_model().
        asr = FasterWhisperASR()
        assert asr.transcribe(b"") == ""

    def test_groq_empty_audio_returns_empty_string(self):
        # No client/network: empty returns before _ensure_client().
        assert GroqWhisperASR(api_key="x").transcribe(b"") == ""


class TestGroqWavPacking:
    """Groq wants an audio file: raw PCM is wrapped in WAV, WAV passes through."""

    def test_raw_pcm_wrapped_in_wav(self):
        pcm = np.array([0, 1000, -1000, 32767], dtype="<i2").tobytes()
        wav = GroqWhisperASR._to_wav_bytes(pcm, 16_000)

        assert wav[:4] == b"RIFF"
        with wave.open(io.BytesIO(wav), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 16_000
            assert w.readframes(w.getnframes()) == pcm

    def test_existing_wav_passed_through(self):
        samples = np.array([0, 16384, -16384], dtype=np.int16)
        wav = _make_wav(samples, rate=16_000)
        assert GroqWhisperASR._to_wav_bytes(wav, 16_000) is wav


class TestWavDecoding:
    """_to_float32_mono converts WAV/PCM to mono float32 @ 16 kHz."""

    def test_wav_decoded_to_normalized_float32(self):
        samples = np.array([0, 16384, -16384, 32767], dtype=np.int16)
        wav = _make_wav(samples, rate=16_000)

        decoded = FasterWhisperASR._to_float32_mono(wav, 16_000)

        assert decoded.dtype == np.float32
        assert decoded.shape == (4,)
        assert decoded[0] == pytest.approx(0.0)
        assert decoded[1] == pytest.approx(0.5, abs=1e-4)
        assert decoded[2] == pytest.approx(-0.5, abs=1e-4)
        assert decoded[3] == pytest.approx(1.0, abs=1e-3)

    def test_wav_resampled_to_16k(self):
        # 4 samples @ 8 kHz -> 0.5 ms -> 8 samples @ 16 kHz.
        samples = np.array([0, 8000, -8000, 16000], dtype=np.int16)
        wav = _make_wav(samples, rate=8_000)

        decoded = FasterWhisperASR._to_float32_mono(wav, 8_000)

        assert decoded.dtype == np.float32
        assert decoded.shape == (8,)

    def test_raw_pcm_decoded(self):
        samples = np.array([0, 16384, -16384], dtype=np.int16)
        raw = samples.astype("<i2").tobytes()

        decoded = FasterWhisperASR._to_float32_mono(raw, 16_000)

        assert decoded.dtype == np.float32
        assert decoded.shape == (3,)
        assert decoded[1] == pytest.approx(0.5, abs=1e-4)


class TestVoicePipeline:
    """The audio-in -> agent -> audio-out orchestration, with fakes."""

    def test_greeting_audio_synthesizes_session_greeting(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts)

        audio = pipeline.greeting_audio()

        assert audio == b"AUDIO:Labas!"
        assert tts.calls == [("Labas!", "lt")]  # language pulled from session config

    def test_filler_audio_synthesized_once_and_cached(self):
        """The 'let me check' cue (step 2.2) is synthesized once, then cached."""
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts)

        a1 = pipeline.filler_audio()
        a2 = pipeline.filler_audio()

        assert a1.startswith(b"AUDIO:")
        assert "Sekundėlę" in a1.decode("utf-8")  # LT cue from session language
        assert a1 == a2
        assert len(tts.calls) == 1  # cached, not re-synthesized

    def test_stream_turn_yields_one_chunk_per_sentence(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeStreamingTTS()
        session.handle_turn = lambda t: "Sveiki. Ar veikia?"
        pipeline = VoicePipeline(session, asr, tts)

        chunks = list(pipeline.stream_turn(b"pcm"))

        assert chunks == [b"A:Sveiki.", b"A:Ar veikia?"]

    def test_stream_turn_falls_back_when_tts_not_streaming(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()  # synthesize only
        pipeline = VoicePipeline(session, asr, tts)

        chunks = list(pipeline.stream_turn(b"pcm"))

        assert chunks == [b"AUDIO:atsakymas: neveikia internetas"]

    def test_stream_turn_drops_noise(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeStreamingTTS()
        pipeline = VoicePipeline(session, asr, tts, noise_filter=lambda t: True)

        assert list(pipeline.stream_turn(b"pcm")) == []

    def test_stream_turn_buffers_agent_tokens_into_sentence_tts(self):
        """C3: an agent token stream is buffered to sentences and TTS'd each."""
        session, asr, tts = _FakeStreamingSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts)

        chunks = list(pipeline.stream_turn(b"pcm"))

        # "Svei|ki. |Ar |veikia?" -> sentences "Sveiki." then "Ar veikia?"
        assert chunks == [b"AUDIO:Sveiki.", b"AUDIO:Ar veikia?"]

    def test_stream_turn_reports_where_the_time_went(self):
        """Review finding AM: one turn_timing event per streamed turn — ASR, the
        agent's first token, the first sentence, the first audio and the total, in
        ms from the turn start and in that order."""
        events = []
        session, asr, tts = _FakeStreamingSession(), _FakeASR(), _FakeTTS()
        session.tracer = SimpleNamespace(emit=lambda event, **f: events.append((event, f)))
        pipeline = VoicePipeline(session, asr, tts)

        list(pipeline.stream_turn(b"pcm"))

        timing = [f for e, f in events if e == "turn_timing"]
        assert len(timing) == 1
        t = timing[0]
        assert t["sentences"] == 2 and t["reused_partial"] is False
        order = ["asr_ms", "first_token_ms", "first_sentence_ms", "first_audio_ms", "total_ms"]
        values = [t[k] for k in order]
        assert values == sorted(values)

    def test_stream_turn_timing_is_emitted_when_the_caller_barges_in(self):
        events = []
        session, asr, tts = _FakeStreamingSession(), _FakeASR(), _FakeTTS()
        session.tracer = SimpleNamespace(emit=lambda event, **f: events.append((event, f)))
        pipeline = VoicePipeline(session, asr, tts)

        chunks = list(pipeline.stream_turn(b"pcm", should_stop=lambda: True))

        assert chunks == []
        timing = [f for e, f in events if e == "turn_timing"]
        assert len(timing) == 1 and timing[0]["cancelled"] == 1

    def test_handle_audio_runs_full_turn(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts)

        turn = pipeline.handle_audio(b"rawpcm", sample_rate=8_000)

        assert isinstance(turn, VoiceTurn)
        assert turn.transcript == "neveikia internetas"
        assert turn.reply_text == "atsakymas: neveikia internetas"
        assert turn.reply_audio == b"AUDIO:atsakymas: neveikia internetas"
        assert turn.is_complete is False
        # ASR got the audio + session language + sample rate; agent saw the transcript.
        assert asr.calls == [(b"rawpcm", "lt", 8_000)]
        assert session.turns == ["neveikia internetas"]

    def test_explicit_language_overrides_session(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts, language="en")

        pipeline.handle_audio(b"x")

        assert asr.calls[0][1] == "en"
        assert tts.calls[0][1] == "en"

    def test_transcript_filter_applied_before_agent(self):
        # The filter (e.g. number normalization) runs on the transcript the
        # agent receives, not the raw ASR text.
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts, transcript_filter=str.upper)

        turn = pipeline.handle_audio(b"x")

        assert turn.transcript == "NEVEIKIA INTERNETAS"
        assert session.turns == ["NEVEIKIA INTERNETAS"]

    def test_asr_event_carries_raw_and_normalized(self):
        class _CaptureTracer:
            def __init__(self):
                self.events = []

            def emit(self, event_type, **fields):
                self.events.append({"type": event_type, **fields})

        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        session.tracer = _CaptureTracer()
        # filter uppercases -> raw differs from transcript the agent receives.
        pipeline = VoicePipeline(session, asr, tts, transcript_filter=str.upper)

        pipeline.handle_audio(b"x")

        asr_ev = [e for e in session.tracer.events if e["type"] == "asr"]
        assert len(asr_ev) == 1
        assert asr_ev[0]["raw"] == "neveikia internetas"
        assert asr_ev[0]["transcript"] == "NEVEIKIA INTERNETAS"
        assert "ms" in asr_ev[0]

    def test_noise_turn_is_dropped_agent_not_called(self):
        # A noise/hallucination transcript -> agent is NOT called, reply empty.
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts, noise_filter=lambda t: True)

        turn = pipeline.handle_audio(b"x")

        assert turn.reply_text == ""
        assert turn.reply_audio == b""
        assert session.turns == []  # handle_turn never ran
        assert tts.calls == []  # nothing synthesized

    def test_non_noise_turn_runs_normally(self):
        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts, noise_filter=lambda t: False)

        turn = pipeline.handle_audio(b"x")

        assert turn.reply_text == "atsakymas: neveikia internetas"
        assert session.turns == ["neveikia internetas"]

    def test_voice_latency_emitted_to_session_tracer(self):
        class _CaptureTracer:
            def __init__(self):
                self.events = []

            def emit(self, event_type, **fields):
                self.events.append({"type": event_type, **fields})

        session, asr, tts = _FakeSession(), _FakeASR(), _FakeTTS()
        session.tracer = _CaptureTracer()
        pipeline = VoicePipeline(session, asr, tts)

        pipeline.handle_audio(b"x")

        lat = [e for e in session.tracer.events if e["type"] == "voice_latency"]
        assert len(lat) == 1
        assert {"asr_ms", "agent_ms", "tts_ms", "total_ms"} <= set(lat[0])

    def test_handle_audio_reports_per_stage_latency(self):
        # A slow ASR proves the stage timer measures real wall-clock, not 0.
        class _SlowASR(_FakeASR):
            def transcribe(self, audio, *, language=None, sample_rate=16_000):
                import time

                time.sleep(0.005)
                return super().transcribe(audio, language=language, sample_rate=sample_rate)

        session, asr, tts = _FakeSession(), _SlowASR(), _FakeTTS()
        pipeline = VoicePipeline(session, asr, tts)

        turn = pipeline.handle_audio(b"x")

        assert turn.asr_ms >= 5.0  # the 5 ms sleep is counted in the ASR stage
        assert turn.agent_ms >= 0.0
        assert turn.tts_ms >= 0.0


@pytest.mark.integration
class TestVoiceIntegration:
    """Real engines/network — skipped unless the `voice` extra is installed."""

    def test_gtts_synthesizes_mp3(self):
        pytest.importorskip("gtts")
        tts = GTTSProvider()
        try:
            audio = tts.synthesize("Labas", language="lt")
        except Exception as exc:  # network/lookup failures shouldn't fail CI
            pytest.skip(f"gTTS unavailable (network?): {exc}")
        assert audio[:3] == b"ID3" or len(audio) > 0  # MP3 payload


# Merged from test_streaming_tts.py (2026-08-05 cleanup): one file per
# component — sentence-split + streaming synthesis belong to the voice block.
from unittest.mock import patch

import pytest


class TestSplitSentences:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Sveiki. Ar veikia?", ["Sveiki.", "Ar veikia?"]),
            ("Vienas sakinys", ["Vienas sakinys"]),
            ("A! B? C.", ["A!", "B?", "C."]),
            ("Eilutė viena\nEilutė dvi", ["Eilutė viena", "Eilutė dvi"]),
            ("   ", []),
            ("", []),
        ],
    )
    def test_split(self, text, expected):
        from adapters.tts import split_sentences

        assert split_sentences(text) == expected


class TestGTTSStream:
    def test_stream_yields_one_blob_per_sentence(self):
        from adapters.tts import GTTSProvider

        tts = GTTSProvider()
        with patch.object(
            tts, "synthesize", side_effect=lambda s, language=None: b"A:" + s.encode()
        ):
            chunks = list(tts.stream("Sveiki. Ar veikia?"))

        assert chunks == [b"A:Sveiki.", b"A:Ar veikia?"]

    def test_empty_text_streams_nothing(self):
        from adapters.tts import GTTSProvider

        assert list(GTTSProvider().stream("")) == []


class TestEdgeTTS:
    def test_conforms_to_streaming_port(self):
        from adapters.tts import EdgeTTSProvider
        from ports.tts import StreamingTTSProvider, TTSProvider

        tts = EdgeTTSProvider()
        assert isinstance(tts, TTSProvider)
        assert isinstance(tts, StreamingTTSProvider)

    def test_voice_selection(self):
        from adapters.tts import EdgeTTSProvider

        assert EdgeTTSProvider()._voice_for("lt") == "lt-LT-LeonasNeural"  # male, default
        assert EdgeTTSProvider()._voice_for("en") == "en-US-GuyNeural"
        assert EdgeTTSProvider()._voice_for(None) == "lt-LT-LeonasNeural"  # default lt
        assert EdgeTTSProvider(voice="custom")._voice_for("lt") == "custom"

    def test_stream_chunks_by_sentence(self):
        from adapters.tts import EdgeTTSProvider

        tts = EdgeTTSProvider()
        with patch.object(tts, "_synthesize_one", side_effect=lambda s, v: b"E:" + s.encode()):
            chunks = list(tts.stream("Sveiki. Ar veikia?"))

        assert chunks == [b"E:Sveiki.", b"E:Ar veikia?"]

    def test_synthesize_joins_sentences(self):
        from adapters.tts import EdgeTTSProvider

        tts = EdgeTTSProvider()
        with patch.object(tts, "_synthesize_one", side_effect=lambda s, v: b"E:" + s.encode()):
            assert tts.synthesize("A. B.") == b"E:A.E:B."

    def test_one_failed_sentence_does_not_break_stream(self):
        from adapters.tts import EdgeTTSProvider

        tts = EdgeTTSProvider()

        def flaky(sentence, voice):
            if "B" in sentence:
                raise RuntimeError("network")
            return b"E:" + sentence.encode()

        with patch.object(tts, "_synthesize_one", side_effect=flaky):
            chunks = list(tts.stream("A. B. C."))

        assert chunks == [b"E:A.", b"E:C."]

    def test_real_edge_synthesis_smoke(self):
        """Opt-in: real edge-tts call. Skips if edge/network unavailable."""
        from adapters.tts import EdgeTTSProvider

        try:
            audio = EdgeTTSProvider()._synthesize_one("Sveiki.", "lt-LT-OnaNeural")
        except Exception as e:  # network / engine missing
            pytest.skip(f"edge-tts unavailable: {e}")
        assert isinstance(audio, bytes) and len(audio) > 100  # real MP3
