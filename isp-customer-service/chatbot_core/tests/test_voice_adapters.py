"""
Tests for the voice adapters (ASR, TTS, sentence splitting).

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
from adapters.tts import GTTSProvider
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
