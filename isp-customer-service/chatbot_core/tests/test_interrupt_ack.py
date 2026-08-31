"""
P1b interrupt-ack (2026-08-26 architektūros peržiūra): a caller who CUT the
agent off gets a short cached "Aha, girdžiu." within ~0.8 s while the real
reply is still thinking. Scoped to interrupted turns only.
"""

import threading
import time
from types import SimpleNamespace

import agent.identification  # noqa: F401  (warm the deferred import — cold it

# costs ~2 s and the ack would lose its race against the REAL chunk in tests;
# in a live process it is always warm)


def _ms(prev_cancelled: bool, delay_s: float):
    """A ManagedSession stand-in whose pipeline sleeps before replying."""

    class _SlowPipeline:
        def __init__(self) -> None:
            self.prev_cancelled = prev_cancelled
            self.last_turn_aligned = True
            self.last_turn_sentences = []

        def stream_turn(self, audio, **kwargs):
            time.sleep(delay_s)
            yield b"REAL"

    return SimpleNamespace(
        voice=_SlowPipeline(),
        cancel=threading.Event(),
        turn_count=0,
        session=SimpleNamespace(
            session_id="t",
            is_complete=False,
            tracer=SimpleNamespace(emit=lambda *a, **k: None),
            last_spoken_text=lambda: "",
        ),
    )


def _run(ms, monkeypatch):
    from app import voice

    monkeypatch.setenv("API_RECORD_AUDIO", "0")
    monkeypatch.setenv("SPECULATION", "off")
    monkeypatch.setenv("INTERRUPT_ACK_AFTER_S", "0.1")
    monkeypatch.setattr(voice, "synthesize_text", lambda text: b"ACK")
    chunks: list[bytes] = []
    voice.run_voice_turn_stream(ms, b"RIFF-fake", chunks.append)
    return chunks


def test_interrupted_turn_gets_the_ack_first(monkeypatch):
    chunks = _run(_ms(prev_cancelled=True, delay_s=0.5), monkeypatch)
    assert chunks == [b"ACK", b"REAL"]


def test_fast_reply_needs_no_ack(monkeypatch):
    chunks = _run(_ms(prev_cancelled=True, delay_s=0.0), monkeypatch)
    assert chunks == [b"REAL"]


def test_normal_turn_never_acks(monkeypatch):
    chunks = _run(_ms(prev_cancelled=False, delay_s=0.5), monkeypatch)
    assert chunks == [b"REAL"]


def test_off_switch(monkeypatch):
    monkeypatch.setenv("INTERRUPT_ACK", "off")
    chunks = _run(_ms(prev_cancelled=True, delay_s=0.5), monkeypatch)
    assert chunks == [b"REAL"]
