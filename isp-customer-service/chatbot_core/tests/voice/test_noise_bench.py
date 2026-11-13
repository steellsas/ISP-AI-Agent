"""The noise bench's own arithmetic (scripts/noise_bench.py, I-4/I-5 T2): what it counts as
an error, how loud it makes the room, and where it takes the room from."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

FUNCTION = "Triukšmo stendas"

_PATH = Path(__file__).resolve().parents[3] / "scripts" / "noise_bench.py"
_spec = importlib.util.spec_from_file_location("noise_bench", _PATH)
bench = importlib.util.module_from_spec(_spec)
sys.modules["noise_bench"] = bench
_spec.loader.exec_module(bench)


class TestWhatCountsAsAnError:
    def test_punctuation_and_case_are_not_errors(self):
        assert bench.cer("Taip, dėl Tilžės g. 60.", "taip dėl tilžės g 60") == 0.0

    def test_a_wrong_letter_is_one_error(self):
        assert bench.cer("tomas", "tamas") == pytest.approx(1 / 5)

    def test_nothing_heard_is_all_wrong(self):
        assert bench.cer("mano vardas tomas", "") == 1.0


class TestTheRoom:
    def test_mixed_at_the_asked_ratio(self):
        rng = np.random.default_rng(0)
        speech = (rng.standard_normal(8000) * 3000).astype(np.int16)
        noise = (rng.standard_normal(8000) * 500).astype(np.int16)
        out = bench.mix(speech, noise, 10.0)
        added = out.astype(float) - speech
        ratio = 20 * np.log10(np.std(speech.astype(float)) / np.std(added))
        assert ratio == pytest.approx(10.0, abs=0.3)

    def test_as_recorded_keeps_the_room_level(self):
        speech = np.zeros(800, np.int16)
        noise = np.full(800, 100, np.int16)
        assert np.all(bench.mix(speech, noise, None) == 100)

    def test_scaled_to_a_level(self):
        x = (np.sin(np.arange(8000) / 5) * 1000).astype(np.int16)
        assert bench.dbfs(bench.scale_to(x, -20.0)) == pytest.approx(-20.0, abs=0.1)


class TestWhereTheRoomComesFrom:
    def test_caller_and_agent_are_cut_out(self):
        timeline = [
            {"t": 0.0, "kind": "start"},
            {"t": 2.0, "kind": "agent_start"},
            {"t": 5.0, "kind": "agent_stop"},
            {"t": 10.0, "kind": "vad_start"},
            {"t": 12.0, "kind": "vad_stop"},
        ]
        spans = bench.background_spans(timeline, 20.0)
        assert spans == [(0.0, 1.6), (5.8, 9.6), (12.4, 20.0)]

    def test_marks_from_before_the_fix_are_twice_as_long(self):
        # Before the 8 kHz fix a turn file said 16 kHz: its length in the mark is half.
        timeline = [{"t": 10.0, "kind": "asr", "start": 9.0, "end": 10.0}]
        assert bench.background_spans(timeline, 20.0, asr_scale=2.0) == [
            (0.0, 7.6),
            (10.4, 20.0),
        ]
