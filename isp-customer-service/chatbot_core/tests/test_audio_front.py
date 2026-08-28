"""
D2 duplex — the server-side audio front: VAD, segmenting, semantic endpoint
windows, partial cadence, busy-turn stash. Pure state machine over frames —
time is sample-carried, so everything here is deterministic.
"""

import struct

from app.audio_front import AudioFront, pcm_from_wav, wav_bytes

RATE = 16_000


def _frame(loud: bool, samples: int = 4096) -> bytes:
    """One client frame: 4096 samples @16k = 256 ms."""
    val = 5000 if loud else 0
    pcm = struct.pack(f"<{samples}h", *([val] * samples))
    return wav_bytes(pcm, RATE)


class TestWavHelpers:
    def test_roundtrip(self):
        pcm = struct.pack("<4h", 1, -2, 3, -4)
        wav = wav_bytes(pcm, RATE)
        got_pcm, got_rate = pcm_from_wav(wav)
        assert got_pcm == pcm and got_rate == RATE

    def test_rejects_non_wav(self):
        import pytest

        with pytest.raises(ValueError):
            pcm_from_wav(b"garbage")


class TestEndpointing:
    def test_speech_then_default_silence_cuts_one_utterance(self):
        front = AudioFront()
        actions = []
        for _ in range(4):
            actions += front.on_frame(_frame(loud=True))
        for _ in range(4):  # 4 x 256 ms = 1024 ms > 900 ms default window
            actions += front.on_frame(_frame(loud=False))
        kinds = [a for a, _w in actions]
        assert kinds[0] == "speech"
        assert kinds.count("utterance") == 1
        wav = next(w for a, w in actions if a == "utterance")
        pcm, rate = pcm_from_wav(wav)
        # the segment carries the speech AND the trailing silence frames
        assert rate == RATE and len(pcm) >= 4 * 4096 * 2

    def test_fast_hint_shrinks_the_window(self):
        front = AudioFront()
        for _ in range(4):
            front.on_frame(_frame(loud=True))
        front.set_hint("fast", 350)
        acts = front.on_frame(_frame(loud=False))  # 256 ms < 350
        assert acts == []
        acts = front.on_frame(_frame(loud=False))  # 512 ms >= 350
        assert [a for a, _w in acts] == ["utterance"]

    def test_slow_hint_stretches_the_window(self):
        front = AudioFront()
        for _ in range(4):
            front.on_frame(_frame(loud=True))
        front.set_hint("slow", 1400)
        acts = []
        for _ in range(5):  # 1280 ms < 1400 — still waiting
            acts += front.on_frame(_frame(loud=False))
        assert acts == []
        acts = front.on_frame(_frame(loud=False))  # 1536 ms >= 1400
        assert [a for a, _w in acts] == ["utterance"]

    def test_sub_word_blip_is_dropped(self):
        front = AudioFront()
        acts = front.on_frame(_frame(loud=True, samples=2048))  # 128 ms < 220
        assert [a for a, _w in acts] == ["speech"]
        acts = []
        for _ in range(4):
            acts += front.on_frame(_frame(loud=False))
        assert acts == []  # endpoint fired but the blip never became a turn

    def test_speech_resumes_resets_the_silence_clock(self):
        front = AudioFront()
        for _ in range(3):
            front.on_frame(_frame(loud=True))
        for _ in range(3):  # 768 ms of pause — under the window
            assert front.on_frame(_frame(loud=False)) == []
        front.on_frame(_frame(loud=True))  # the caller went on talking
        acts = []
        for _ in range(3):
            acts += front.on_frame(_frame(loud=False))
        assert [a for a, _w in acts] == []  # 768 ms again — still one segment
        acts = front.on_frame(_frame(loud=False))
        assert [a for a, _w in acts] == ["utterance"]

    def test_partial_cadence_during_speech(self):
        front = AudioFront()
        acts = []
        for _ in range(8):  # 2048 ms of speech, interval 1000 ms
            acts += front.on_frame(_frame(loud=True))
        assert [a for a, _w in acts].count("partial") == 2


class TestStash:
    def test_stash_concatenates_and_pops_once(self):
        front = AudioFront()
        a = wav_bytes(struct.pack("<2h", 1, 2), RATE)
        b = wav_bytes(struct.pack("<2h", 3, 4), RATE)
        front.stash(a)
        front.stash(b)
        merged = front.pop_stash()
        pcm, _rate = pcm_from_wav(merged)
        assert pcm == struct.pack("<4h", 1, 2, 3, 4)
        assert front.pop_stash() is None


class TestDuckAndReuse:
    def test_abort_segment_drops_open_speech(self):
        front = AudioFront()
        front.on_frame(_frame(loud=True))
        front.abort_segment()
        acts = []
        for _ in range(4):
            acts += front.on_frame(_frame(loud=False))
        assert acts == []  # the echo audio never became a turn

    def test_reuse_ok_when_last_snapshot_covers_all_speech(self):
        front = AudioFront()
        acts = []
        for _ in range(4):  # partial fires on the 4th frame (1024 ms)
            acts += front.on_frame(_frame(loud=True))
        assert [a for a, _w in acts].count("partial") == 1
        front.snap_done()  # the ws handler confirmed its ASR
        for _ in range(4):  # silence only — the snapshot still covers everything
            acts += front.on_frame(_frame(loud=False))
        assert [a for a, _w in acts].count("utterance") == 1
        assert front.last_reuse_ok is True

    def test_no_reuse_when_speech_continues_after_snapshot(self):
        front = AudioFront()
        for _ in range(4):
            front.on_frame(_frame(loud=True))
        front.snap_done()
        front.on_frame(_frame(loud=True))  # they said MORE after the snapshot
        for _ in range(4):
            front.on_frame(_frame(loud=False))
        assert front.last_reuse_ok is False

    def test_no_reuse_when_snapshot_was_skipped(self):
        front = AudioFront()
        for _ in range(4):
            front.on_frame(_frame(loud=True))
        front.snap_skipped()  # partial task was busy — no text exists
        for _ in range(4):
            front.on_frame(_frame(loud=False))
        assert front.last_reuse_ok is False

    def test_long_speech_backchannel_moment_once(self):
        front = AudioFront()
        acts = []
        for _ in range(20):  # 5120 ms of speech
            acts += front.on_frame(_frame(loud=True))
        assert [a for a, _w in acts].count("long_speech") == 1


class TestInterruptFastWindow:
    """P1 (live 2026-08-26: TTFA after a duck-cut hit 6-10 s): a confirmed
    interruption closes its segment on the FAST window; a slow hint (unfinished
    thought) still outranks it; the flag dies with the segment."""

    def test_cut_segment_closes_fast(self):
        front = AudioFront()
        for _ in range(3):
            front.on_frame(_frame(loud=True))
        front.mark_interrupt()  # the duck ruling said CUT
        acts = front.on_frame(_frame(loud=False))  # 256 ms < 350
        assert acts == []
        acts = front.on_frame(_frame(loud=False))  # 512 ms >= 350
        assert [a for a, _w in acts] == ["utterance"]

    def test_slow_hint_outranks_interrupt_fast(self):
        front = AudioFront()
        for _ in range(3):
            front.on_frame(_frame(loud=True))
        front.mark_interrupt()
        front.set_hint("slow", 1400)  # trailing conjunction — wait anyway
        acts = []
        for _ in range(5):  # 1280 ms < 1400
            acts += front.on_frame(_frame(loud=False))
        assert acts == []

    def test_flag_clears_with_the_segment(self):
        front = AudioFront()
        for _ in range(3):
            front.on_frame(_frame(loud=True))
        front.mark_interrupt()
        for _ in range(2):
            front.on_frame(_frame(loud=False))  # fast cut fired
        for _ in range(3):  # next segment — normal window again
            front.on_frame(_frame(loud=True))
        acts = []
        for _ in range(2):  # 512 ms < 900 default
            acts += front.on_frame(_frame(loud=False))
        assert acts == []


class TestOverlayStitching:
    """Duplex-hearing 1.5: long think-pauses do not chop the overlay capture,
    and a segment started over the agent's voice continues into the next turn
    in ONE piece."""

    def test_overlay_tolerates_long_pauses(self):
        front = AudioFront(silence_ms_override=4000)
        for _ in range(3):
            front.on_frame(_frame(loud=True))
        acts = []
        for _ in range(13):  # ~3.3 s of pause — under the 4 s overlay window
            acts += front.on_frame(_frame(loud=False))
        assert acts == []  # segment still open, nothing chopped
        for _ in range(3):
            front.on_frame(_frame(loud=True))  # the caller resumes
        acts = []
        for _ in range(16):  # >4 s -> now it closes
            acts += front.on_frame(_frame(loud=False))
        assert [a for a, _w in acts] == ["utterance"]

    def test_export_open_and_adopt_head_stitch(self):
        overlay = AudioFront(silence_ms_override=4000)
        for _ in range(3):
            overlay.on_frame(_frame(loud=True))  # talking over the agent
        head = overlay.export_open()
        assert head and not overlay._in_speech
        main = AudioFront()
        main.adopt_head(head)
        acts = []
        for _ in range(2):
            acts += main.on_frame(_frame(loud=True))  # keeps talking
        for _ in range(4):
            acts += main.on_frame(_frame(loud=False))
        utt = [w for a, w in acts if a == "utterance"]
        assert len(utt) == 1
        pcm, _rate = pcm_from_wav(utt[0])
        assert len(pcm) >= len(head) + 2 * 4096 * 2  # head + the continuation

    def test_export_open_empty_when_idle(self):
        assert AudioFront().export_open() is None
