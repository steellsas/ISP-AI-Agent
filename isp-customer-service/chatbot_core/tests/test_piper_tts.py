"""Piper adapter: voice choice, knobs, fallback to edge-tts, and (when the voices are
downloaded) real offline synthesis to per-sentence MP3 blobs."""

import importlib.util

import pytest
from adapters.tts import EdgeTTSProvider, PiperTTSProvider
from adapters.tts.piper_tts import VOICES, missing_files, models_dir
from ports.tts import StreamingTTSProvider

_READY = (
    importlib.util.find_spec("piper") is not None
    and importlib.util.find_spec("lameenc") is not None
    and not missing_files("reginute")
    and not missing_files("ingute")
)
needs_voices = pytest.mark.skipif(not _READY, reason="run scripts/get_piper_voices.py")


def _is_mp3(blob: bytes) -> bool:
    return blob[:3] == b"ID3" or (blob[0] == 0xFF and blob[1] & 0xE0 == 0xE0)


class TestConstruction:
    def test_unknown_voice_is_refused(self):
        with pytest.raises(ValueError, match="unknown Piper voice"):
            PiperTTSProvider(voice="leonas")

    def test_missing_voice_says_how_to_get_it(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="get_piper_voices"):
            PiperTTSProvider(voice="ingute", root=tmp_path)

    def test_models_dir_follows_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TTS_PIPER_DIR", str(tmp_path))
        assert models_dir() == tmp_path

    def test_both_voices_are_offered_on_the_config_page(self):
        from app.runtime_config import SCHEMA

        items = {item["key"]: item for item in SCHEMA}
        assert items["TTS_ENGINE"]["options"][0] == "piper"
        assert items["TTS_PIPER_VOICE"]["options"] == list(VOICES)


class TestKnobs:
    @pytest.mark.parametrize(
        ("rate", "scale"),
        [(None, 1.3), ("+0%", 1.3), ("+10%", 1.182), ("-10%", 1.444), ("fast", 1.3)],
    )
    def test_rate_scales_the_recipe_tempo(self, monkeypatch, rate, scale):
        if rate is None:
            monkeypatch.delenv("TTS_RATE", raising=False)
        else:
            monkeypatch.setenv("TTS_RATE", rate)
        assert PiperTTSProvider._length_scale() == scale

    @pytest.mark.parametrize(("raw", "value"), [("0.5", 0.5), ("9", 1.0), ("0", 0.3), ("x", 0.667)])
    def test_noise_is_clamped(self, monkeypatch, raw, value):
        monkeypatch.setenv("TTS_PIPER_NOISE", raw)
        assert PiperTTSProvider._noise_scale() == value


class TestBuild:
    def test_falls_back_to_edge_when_the_voice_is_not_downloaded(self, monkeypatch, tmp_path):
        from app import voice

        monkeypatch.setenv("TTS_ENGINE", "piper")
        monkeypatch.setenv("TTS_PIPER_DIR", str(tmp_path))
        voice._build_tts.cache_clear()
        try:
            assert isinstance(voice._build_tts(), EdgeTTSProvider)
        finally:
            voice._build_tts.cache_clear()

    @needs_voices
    @pytest.mark.parametrize("name", list(VOICES))
    def test_builds_the_chosen_voice(self, monkeypatch, name):
        from app import voice

        monkeypatch.setenv("TTS_ENGINE", "piper")
        monkeypatch.setenv("TTS_PIPER_VOICE", name)
        monkeypatch.delenv("TTS_PIPER_DIR", raising=False)
        voice._build_tts.cache_clear()
        try:
            tts = voice._build_tts()
            assert isinstance(tts, PiperTTSProvider)
            assert tts._voice == name
        finally:
            voice._build_tts.cache_clear()


@needs_voices
class TestSynthesis:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self):
        PiperTTSProvider._CACHE.clear()
        yield
        PiperTTSProvider._CACHE.clear()

    @pytest.mark.parametrize("name", list(VOICES))
    def test_one_mp3_blob_per_sentence(self, name):
        tts = PiperTTSProvider(voice=name)
        assert isinstance(tts, StreamingTTSProvider)
        blobs = list(tts.stream("Laba diena. Ar internetas veikia?"))
        assert len(blobs) == 2
        assert all(_is_mp3(b) and len(b) > 2000 for b in blobs)

    def test_sentence_is_cached_and_voice_keyed(self):
        reginute, ingute = PiperTTSProvider(voice="reginute"), PiperTTSProvider(voice="ingute")
        reginute.synthesize("Supratau.")
        assert reginute.is_cached("Supratau.")
        assert not ingute.is_cached("Supratau.")

    def test_dictated_ip_is_spoken_piece_by_piece(self):
        tts = PiperTTSProvider(voice="reginute")
        tts.synthesize("Adresas 192.168.1.1.")
        # cached under the spoken form, so the IP went through speakable()
        assert any("taškas" in key[0] for key in PiperTTSProvider._CACHE)

    def test_empty_text_gives_no_audio(self):
        assert PiperTTSProvider(voice="reginute").synthesize("  ") == b""
