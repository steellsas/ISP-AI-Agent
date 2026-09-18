"""Scripted lines are rendered ahead of any call (review finding AL): a mechanical
turn then plays from the TTS cache instead of waiting on the network."""


class _FakeTTS:
    def __init__(self, cached=()):
        self.calls = []
        self._cached = set(cached)

    def is_cached(self, sentence, *, language=None):
        return sentence in self._cached

    def synthesize(self, text, *, language=None):
        self.calls.append(text)
        self._cached.add(text)
        return b"mp3"


class TestPrewarm:
    def test_each_sentence_is_rendered_once(self):
        from agent.voice_pipeline import prewarm

        tts = _FakeTTS()
        rendered = prewarm(tts, ["Sveiki. Ar veikia?", "Sveiki."], language="lt")

        assert tts.calls == ["Sveiki.", "Ar veikia?"]
        assert rendered == 2

    def test_already_cached_pieces_are_skipped(self):
        from agent.voice_pipeline import prewarm

        tts = _FakeTTS(cached={"Sveiki."})
        assert prewarm(tts, ["Sveiki. Ar veikia?"], language="lt") == 1
        assert tts.calls == ["Ar veikia?"]

    def test_pieces_match_the_streaming_path(self):
        """The cache is keyed by the exact pieces the streaming path synthesizes —
        sentences popped as they complete, then the tail."""
        from agent.voice_pipeline import spoken_sentences

        assert spoken_sentences("Gerai. Palauksiu, kol patikrinsite") == [
            "Gerai.",
            "Palauksiu, kol patikrinsite",
        ]


class TestScriptedLines:
    def test_the_opening_and_fixed_replies_are_included_templates_are_not(self):
        from agent.config import create_config
        from agent.contract.locale import current, phrase
        from app.voice import PREWARM_GROUPS, scripted_lines

        lines = scripted_lines()
        spoken = {v for k, v in current().phrases.items() if k.split(".")[0] in PREWARM_GROUPS}

        assert lines[0] == phrase("system.greeting", company_name=create_config().company_name)
        assert all("{" not in line for line in lines[1:])
        assert set(lines[1:]) <= spoken  # detector / verdict / pack glosses stay out
        assert "detector" not in PREWARM_GROUPS and "pack" not in PREWARM_GROUPS


class TestEdgeDiskCache:
    def test_a_rendered_sentence_survives_a_restart(self, tmp_path, monkeypatch):
        from adapters.tts.edge_tts import EdgeTTSProvider

        monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path))
        tts = EdgeTTSProvider(default_language="lt")
        key = tts._key("Sveiki.", tts._voice_for("lt"))
        tts._cache_put(key, b"mp3-bytes")
        EdgeTTSProvider._CACHE.clear()  # a new process: the memory cache is empty

        assert tts.is_cached("Sveiki.", language="lt")
        assert tts._synthesize_one("Sveiki.", tts._voice_for("lt")) == b"mp3-bytes"

    def test_the_disk_cache_can_be_turned_off(self, tmp_path, monkeypatch):
        from adapters.tts.edge_tts import EdgeTTSProvider

        monkeypatch.setenv("TTS_CACHE_DIR", "off")
        EdgeTTSProvider._CACHE.clear()
        tts = EdgeTTSProvider(default_language="lt")
        tts._cache_put(tts._key("Ačiū.", tts._voice_for("lt")), b"x")
        EdgeTTSProvider._CACHE.clear()

        assert not tts.is_cached("Ačiū.", language="lt")
        assert list(tmp_path.iterdir()) == []
