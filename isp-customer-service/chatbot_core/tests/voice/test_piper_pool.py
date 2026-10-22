"""Piper in worker processes sounds the same as Piper in-process (piper_pool.py)."""

from __future__ import annotations

import pytest
from adapters.tts.piper_tts import missing_files

FUNCTION = "Piper procesai"

pytestmark = pytest.mark.skipif(
    bool(missing_files("reginute")),
    reason="Piper voice not downloaded (scripts/get_piper_voices.py)",
)


SENTENCE = "Patikrinau: paslauga sustabdyta; skola 49 eurai."


@pytest.fixture(scope="module")
def pool():
    from adapters.tts.piper_pool import PooledPiperTTSProvider

    provider = PooledPiperTTSProvider(voice="reginute")
    yield provider
    provider.close()


def test_pool_streams_the_same_audio_as_in_process(pool):
    from adapters.tts.piper_tts import PiperTTSProvider

    local = b"".join(pcm for pcm, _ in PiperTTSProvider(voice="reginute").stream_pcm(SENTENCE))
    PiperTTSProvider._PCM_CACHE.clear()  # the pool must render, not reuse the line above
    pieces = list(pool.stream_pcm(SENTENCE))
    assert len(pieces) > 1  # phrase by phrase, not one blob
    assert {rate for _, rate in pieces} == {22050}
    # The voice samples its timing (noise), so two renders differ by a few per cent.
    assert abs(len(b"".join(pcm for pcm, _ in pieces)) - len(local)) < 0.1 * len(local)


def test_pool_renders_mp3_for_the_dashboard_voice(pool):
    mp3 = pool.synthesize("Labas.")
    assert mp3[:3] == b"ID3" or mp3[:2] == b"\xff\xfb" or len(mp3) > 1000


def test_knobs_travel_with_the_job(pool, monkeypatch):
    slow = sum(len(pcm) for pcm, _ in pool.stream_pcm(SENTENCE))
    monkeypatch.setenv("TTS_RATE", "+30%")
    fast = sum(len(pcm) for pcm, _ in pool.stream_pcm(SENTENCE))
    assert fast < slow


def test_a_line_said_before_comes_from_the_cache(pool):
    import time

    from adapters.tts.piper_tts import PiperTTSProvider

    PiperTTSProvider._PCM_CACHE.clear()
    first = list(pool.stream_pcm("Ačiū, kad paskambinote."))
    t0 = time.perf_counter()
    again = list(pool.stream_pcm("Ačiū, kad paskambinote."))
    assert again == first
    assert time.perf_counter() - t0 < 0.05


def test_the_dashboard_render_fills_the_pcm_cache_too(pool):
    from adapters.tts.piper_tts import PiperTTSProvider

    PiperTTSProvider._PCM_CACHE.clear()
    pool.synthesize("Geros dienos!")  # the old voice path / the startup prewarm
    assert len(list(pool.stream_pcm("Geros dienos!"))) == 1  # cached whole sentence
