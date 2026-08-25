"""
D2 duplex — the server-side AUDIO FRONT: the turn-cut authority.

With DUPLEX=on the client streams PCM frames continuously ("FRAM"+WAV over
the call WebSocket) and STOPS deciding where an utterance ends. This module
owns that decision:

  frames -> ring segment -> server VAD (energy + hysteresis)
         -> rolling partial ASR cadence (E1 machinery, via the ws handler)
         -> semantic endpoint window (E2 hint: fast / slow / normal)
         -> CUT -> one utterance WAV -> the normal voice-turn path

Design rules (agreed 2026-08-25):
  - Pure state machine over frames — it NEVER touches engine state and never
    calls the ASR itself (the ws handler runs partials/turns from the actions
    this module returns), so it stays deterministic and unit-testable.
  - Time is measured in SAMPLES carried by the frames, not wall clock —
    replayable and test-friendly.
  - Speech captured while a turn is busy is STASHED, not dropped (the old
    path threw those frames away — the "deaf while thinking" cascade).
"""

from __future__ import annotations

import logging
import math
import os
import struct
from array import array

logger = logging.getLogger(__name__)

_MIN_SPEECH_MS = 220  # mirrors the client's micMinMs — sub-word blips are noise
_PRE_FRAMES = 2  # frames kept before speech onset (the word's quiet start)
_MAX_SEGMENT_S = 30.0  # force a cut — never grow a segment unbounded


def _env_f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


def vad_threshold() -> float:
    return _env_f("SERVER_VAD_THR", 0.010)


def default_silence_ms() -> int:
    return int(_env_f("SERVER_SIL_MS", 900))


def partial_interval_ms() -> int:
    return int(_env_f("PARTIAL_INTERVAL_S", 1.0) * 1000)


def pcm_from_wav(frame: bytes) -> tuple[bytes, int]:
    """(pcm16le, rate) from one client frame (the fixed 44-byte header our
    client's wavEncode writes). Raises on anything that is not that layout."""
    if len(frame) < 44 or frame[:4] != b"RIFF" or frame[8:12] != b"WAVE":
        raise ValueError("not a client WAV frame")
    rate = struct.unpack_from("<I", frame, 24)[0]
    return frame[44:], rate


def wav_bytes(pcm: bytes, rate: int) -> bytes:
    """One utterance WAV (16-bit mono) from raw PCM — the same layout the
    client's wavEncode produces, so the whole downstream path is unchanged."""
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(pcm))
        + pcm
    )


def _rms(pcm: bytes) -> float:
    samples = array("h", pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768.0


class AudioFront:
    """Per-call front. `on_frame` returns a list of actions for the transport:
    ("partial", wav)   — run a rolling partial on the segment-so-far
    ("utterance", wav) — the endpoint fired: run a full voice turn
    """

    def __init__(self) -> None:
        self._rate = 16_000
        self._pre: list[bytes] = []  # last frames before speech onset
        self._seg = bytearray()  # current segment PCM (speech + trailing silence)
        self._in_speech = False
        self._speech_ms = 0.0
        self._sil_ms = 0.0
        self._since_partial_ms = 0.0
        # E2 hint from the LAST completed partial: silence window for the cut.
        self._hint_window_ms: int | None = None
        # Speech that completed while a turn was busy — dispatched right after.
        self._stash_pcm = bytearray()

    # -- the E2 feedback loop (ws handler calls this when a partial returns) --

    def set_hint(self, mode: str | None, silence_ms: int | None) -> None:
        self._hint_window_ms = int(silence_ms) if mode in ("fast", "slow") and silence_ms else None

    # -- busy-turn stash (never drop caller speech) ---------------------------

    def stash(self, wav: bytes) -> None:
        try:
            pcm, self._rate = pcm_from_wav(wav)
            self._stash_pcm.extend(pcm)
        except ValueError:  # pragma: no cover - own wav_bytes output always parses
            logger.debug("stash: unparseable wav dropped")

    def pop_stash(self) -> bytes | None:
        if not self._stash_pcm:
            return None
        wav = wav_bytes(bytes(self._stash_pcm), self._rate)
        self._stash_pcm = bytearray()
        return wav

    # -- the state machine ----------------------------------------------------

    def on_frame(self, frame: bytes) -> list[tuple[str, bytes]]:
        try:
            pcm, rate = pcm_from_wav(frame)
        except ValueError:
            return []
        if rate:
            self._rate = rate
        frame_ms = (len(pcm) / 2) / self._rate * 1000.0
        loud = _rms(pcm) > vad_threshold()
        actions: list[tuple[str, bytes]] = []

        if not self._in_speech:
            if loud:
                self._in_speech = True
                self._seg = bytearray(b"".join(self._pre))  # the word's quiet start
                self._seg.extend(pcm)
                self._speech_ms = frame_ms
                self._sil_ms = 0.0
                self._since_partial_ms = frame_ms  # the onset frame counts too
                self._hint_window_ms = None
                actions.append(("speech", b""))  # transport: disarm the check-in
            else:
                self._pre.append(pcm)
                if len(self._pre) > _PRE_FRAMES:
                    self._pre.pop(0)
            return actions

        # in speech: the segment collects EVERYTHING (speech and pauses alike)
        self._seg.extend(pcm)
        if loud:
            self._speech_ms += frame_ms
            self._sil_ms = 0.0
            self._since_partial_ms += frame_ms
            if self._speech_ms >= 600 and self._since_partial_ms >= partial_interval_ms():
                self._since_partial_ms = 0.0
                actions.append(("partial", wav_bytes(bytes(self._seg), self._rate)))
        else:
            self._sil_ms += frame_ms

        window = self._hint_window_ms or default_silence_ms()
        seg_s = (len(self._seg) / 2) / self._rate
        if self._sil_ms >= window or seg_s >= _MAX_SEGMENT_S:
            if self._speech_ms >= _MIN_SPEECH_MS:
                actions.append(("utterance", wav_bytes(bytes(self._seg), self._rate)))
            self._in_speech = False
            self._seg = bytearray()
            self._pre = []
            self._speech_ms = self._sil_ms = self._since_partial_ms = 0.0
            self._hint_window_ms = None
        return actions
