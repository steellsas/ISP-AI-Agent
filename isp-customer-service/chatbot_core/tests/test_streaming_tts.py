"""
Tests for the streaming TTS port + adapters (Pillar C1).

The chunking contract is tested offline (the network synth is mocked); one opt-in
test does a real edge-tts call and skips if there is no network.

Run: pytest tests/test_streaming_tts.py -v
"""

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

        assert EdgeTTSProvider()._voice_for("lt") == "lt-LT-OnaNeural"
        assert EdgeTTSProvider()._voice_for("en") == "en-US-AriaNeural"
        assert EdgeTTSProvider()._voice_for(None) == "lt-LT-OnaNeural"  # default lt
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
