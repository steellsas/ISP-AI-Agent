"""The caller's audio as the line carries it: a phone line in the dashboard, and the whole
caller side kept before VAD — the ground the voice filters are measured on (I-4, I-5)."""

from __future__ import annotations

import asyncio
import json
import wave

import numpy as np
import pytest

pytest.importorskip("pipecat")

from app.call_audio import (  # noqa: E402
    PhoneLineFilter,
    RawCallTrack,
    ulaw_decode,
    ulaw_encode,
)

FUNCTION = "Skambučio garsas prieš VAD"

RATE = 16000


def tone(freq: float, secs: float = 1.0, amp: int = 8000) -> np.ndarray:
    t = np.arange(int(RATE * secs)) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def through_line(pcm: np.ndarray, chunk: int = 320, rate: int = RATE) -> np.ndarray:
    """Through the phone line in 20 ms chunks, as the transport feeds it."""
    line = PhoneLineFilter()
    asyncio.run(line.start(rate))
    out = [
        np.frombuffer(line.line(pcm[i : i + chunk].tobytes()), dtype=np.int16)
        for i in range(0, len(pcm), chunk)
    ]
    return np.concatenate(out)


def energy(pcm: np.ndarray) -> float:
    return float(np.mean(pcm.astype(np.float64) ** 2))


class TestThePhoneLine:
    def test_mu_law_keeps_speech_levels(self):
        pcm = np.array([0, 1, -1, 100, -100, 1000, -1000, 12000, -12000, 32767, -32768])
        back = ulaw_decode(ulaw_encode(pcm))
        # μ-law is logarithmic: the step grows with the level, never more than ~1/16 of it.
        assert np.all(np.abs(back.astype(int) - pcm) <= np.maximum(np.abs(pcm) / 16, 8) + 1)

    def test_mu_law_matches_the_standard_table(self):
        audioop = pytest.importorskip("audioop")
        codes = np.arange(256, dtype=np.uint8)
        assert ulaw_decode(codes).tobytes() == audioop.ulaw2lin(codes.tobytes(), 2)
        # audioop drops the two low bits first: at a few hundred step edges it rounds one
        # code lower — inaudible, and the decoding table above is the one a line plays.
        pcm = np.arange(-32768, 32768, dtype=np.int16)
        theirs = np.frombuffer(audioop.lin2ulaw(pcm.tobytes(), 2), np.uint8).astype(int)
        diff = np.abs(ulaw_encode(pcm).astype(int) - theirs)
        assert diff.max() <= 1 and np.count_nonzero(diff) < 0.01 * len(pcm)

    def test_speech_band_passes(self):
        pcm = tone(800)
        out = through_line(pcm)
        assert len(pcm) - len(out) < RATE * 0.15  # the resamplers hold back ~120 ms
        assert energy(out[RATE // 10 :]) > 0.7 * energy(pcm)

    def test_at_8_khz_the_line_adds_no_delay(self):
        pcm = tone(800)[::2]  # 8 kHz, as the transport hands it in phone mode
        out = through_line(pcm, chunk=160, rate=8000)
        assert len(out) == len(pcm)
        assert energy(out) > 0.95 * energy(pcm)

    def test_above_the_phone_band_is_gone(self):
        # 8 kHz sampling carries nothing above 4 kHz — a 6 kHz hiss does not reach the ASR.
        out = through_line(tone(6000))
        assert energy(out[RATE // 10 :]) < 0.01 * energy(tone(6000))


class TestTheWholeCallerSide:
    def test_every_sample_is_kept_with_its_timeline(self, tmp_path):
        track = RawCallTrack(tmp_path, "phone")
        track.mark("ignored")  # nothing heard yet: no timeline
        for _ in range(50):  # 1 s in 20 ms frames
            track.audio(np.zeros(320, np.int16).tobytes(), RATE)
        track.mark("asr", start=0.2, end=0.8, transcript="neveikia internetas")
        track.close()

        with wave.open(str(tmp_path / "call_caller_raw.wav")) as w:
            assert w.getframerate() == RATE
            assert w.getnframes() == RATE
        lines = [
            json.loads(x)
            for x in (tmp_path / "call_timeline.jsonl").read_text("utf-8").splitlines()
        ]
        assert [x["kind"] for x in lines] == ["start", "asr", "end"]
        assert lines[0]["line"] == "phone" and lines[0]["rate"] == RATE
        assert lines[1]["t"] == 1.0 and lines[1]["transcript"] == "neveikia internetas"

    def test_off_when_recording_is_off(self, tmp_path):
        track = RawCallTrack(None, "browser")
        track.audio(np.zeros(320, np.int16).tobytes(), RATE)
        track.mark("asr")
        track.close()
        assert track.t == 0.0
        assert list(tmp_path.iterdir()) == []

    def test_a_failed_write_never_breaks_the_call(self, tmp_path):
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("x")
        track = RawCallTrack(blocker, "browser")
        track.audio(np.zeros(320, np.int16).tobytes(), RATE)  # cannot open: logged, stops
        track.audio(np.zeros(320, np.int16).tobytes(), RATE)
        track.mark("asr")
        track.close()
