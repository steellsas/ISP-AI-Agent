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

import numpy as np
import pytest
from adapters.asr import FasterWhisperASR, GroqWhisperASR
from adapters.transport import FastRTCVoiceTransport
from adapters.tts import GTTSProvider
from agent.voice_pipeline import VoicePipeline, VoiceTurn
from ports.asr import ASRProvider
from ports.transport import Transport
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


class TestFastRTCTransport:
    """Audio bridging between FastRTC frames and the pipeline (offline)."""

    def test_is_transport(self):
        # Structural Protocol check — start/stop exist; no engine needed.
        transport = FastRTCVoiceTransport(object())
        assert isinstance(transport, Transport)

    def test_incoming_int16_frame_to_pcm(self):
        # FastRTC delivers (sample_rate, (1, N) int16); we want raw PCM + rate.
        frame = np.array([[0, 1000, -1000, 32767]], dtype=np.int16)
        pcm, rate = FastRTCVoiceTransport._incoming_to_pcm16((48_000, frame))

        assert rate == 48_000
        assert np.frombuffer(pcm, dtype="<i2").tolist() == [0, 1000, -1000, 32767]

    def test_incoming_float32_frame_scaled_to_int16(self):
        frame = np.array([[0.0, 0.5, -0.5, 1.0]], dtype=np.float32)
        pcm, rate = FastRTCVoiceTransport._incoming_to_pcm16((16_000, frame))

        decoded = np.frombuffer(pcm, dtype="<i2")
        assert rate == 16_000
        assert decoded[0] == 0
        assert decoded[1] == pytest.approx(16383, abs=2)  # 0.5 * 32767
        assert decoded[3] == 32767

    def test_decode_empty_audio_returns_empty_frame(self):
        # Empty TTS bytes must not touch the (deferred) av decoder.
        out = FastRTCVoiceTransport._decode_audio_to_int16(b"", 24_000)
        assert out.dtype == np.int16
        assert out.shape == (1, 0)

    def test_record_saves_caller_pcm_as_wav(self, tmp_path):
        transport = FastRTCVoiceTransport(object(), record_dir=tmp_path)
        pcm = np.array([0, 1000, -1000, 32767], dtype="<i2").tobytes()

        transport._save_audio("01_user", pcm, kind="pcm", sample_rate=16_000)

        wav_path = tmp_path / "01_user.wav"
        assert wav_path.exists()
        with wave.open(str(wav_path), "rb") as w:
            assert w.getframerate() == 16_000
            assert w.readframes(w.getnframes()) == pcm

    def test_record_disabled_is_noop(self, tmp_path):
        transport = FastRTCVoiceTransport(object())  # no record_dir
        transport._save_audio("01_user", b"\x00\x01", kind="pcm")
        assert list(tmp_path.iterdir()) == []


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

    def test_decode_gtts_mp3_to_fastrtc_frame(self):
        # End-to-end of the transport's output path: gTTS MP3 -> int16 (1, N).
        pytest.importorskip("gtts")
        pytest.importorskip("av")
        tts = GTTSProvider()
        try:
            mp3 = tts.synthesize("Labas", language="lt")
        except Exception as exc:
            pytest.skip(f"gTTS unavailable (network?): {exc}")

        frame = FastRTCVoiceTransport._decode_audio_to_int16(mp3, 24_000)
        assert frame.dtype == np.int16
        assert frame.ndim == 2 and frame.shape[0] == 1  # mono (1, N)
        assert frame.shape[1] > 0  # actually decoded some audio
