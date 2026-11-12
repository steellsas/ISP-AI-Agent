"""The caller's audio as the line carries it — the ground for the voice filters (I-4, I-5).

Two pieces, both before VAD:

- `PhoneLineFilter` makes the dashboard sound like a phone: 8 kHz G.711 μ-law, the codec a
  SIP line uses. The call's input then runs at 8 kHz, as a phone call does (the transport
  resamples, VAD works at 8 kHz, Smart Turn and Whisper resample themselves), so the line
  adds no delay; at another rate the filter resamples down and back itself. A browser call is cleaner than any phone
  call (48 kHz, the browser's own noise suppression), so a filter tuned on it would be tuned
  on the wrong sound. On for `PHONE_LINE=on`; the browser then also turns off its own noise
  suppression and level control (the echo canceller stays: a handset has its own).

- `RawCallTrack` keeps the WHOLE caller side, silence and background included, as
  `call_caller_raw.wav`, with `call_timeline.jsonl` beside it: when VAD heard speech, what
  ASR made of it, when the agent spoke. The turn files keep only what VAD let through, so
  the TV between two sentences — the thing a noise filter is measured on — was never kept.
  Time `t` is seconds of caller audio from the call's start (the audio is its own clock).
"""

from __future__ import annotations

import json
import time
import wave
from pathlib import Path

import numpy as np
from loguru import logger
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    FilterControlFrame,
    Frame,
    InputAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

PHONE_RATE = 8000

# --- G.711 μ-law -----------------------------------------------------------------------

_BIAS = 0x84
_CLIP = 32635


def ulaw_encode(pcm: np.ndarray) -> np.ndarray:
    """int16 samples → G.711 μ-law bytes (ITU-T G.711, the table every SIP line uses)."""
    x = pcm.astype(np.int32)
    sign = (x < 0).astype(np.int32)
    x = np.minimum(np.abs(x), _CLIP) + _BIAS
    exponent = np.clip(np.floor(np.log2(x)).astype(np.int32) - 7, 0, 7)
    mantissa = (x >> (exponent + 3)) & 0x0F
    return (~((sign << 7) | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8)


def ulaw_decode(code: np.ndarray) -> np.ndarray:
    """G.711 μ-law bytes → int16 samples."""
    u = (~code.astype(np.int32)) & 0xFF
    exponent = (u >> 4) & 0x07
    x = (((u & 0x0F) << 3) + _BIAS) << exponent
    x -= _BIAS
    return np.where(u & 0x80, -x, x).astype(np.int16)


class PhoneLineFilter(BaseAudioFilter):
    """The caller's audio through a phone line: μ-law and back at 8 kHz. At another input
    rate it resamples down and up around the codec — streaming, LQ (~60 ms each way; HQ
    held back ~170 ms in all, QQ lets a 6 kHz hiss alias into the speech band)."""

    def __init__(self) -> None:
        self._rate = 0
        self._down = None
        self._up = None

    async def start(self, sample_rate: int):
        import soxr

        self._rate = sample_rate
        if sample_rate != PHONE_RATE:
            self._down = soxr.ResampleStream(sample_rate, PHONE_RATE, 1, "int16", "LQ")
            self._up = soxr.ResampleStream(PHONE_RATE, sample_rate, 1, "int16", "LQ")
        logger.info(f"phone line: {sample_rate} Hz in, G.711 μ-law at 8 kHz")

    async def stop(self):
        self._down = self._up = None

    async def process_frame(self, frame: FilterControlFrame):
        pass

    async def filter(self, audio: bytes) -> bytes:
        return self.line(audio)

    def line(self, audio: bytes) -> bytes:
        pcm = np.frombuffer(audio, dtype=np.int16)
        if self._down is not None:
            pcm = self._down.resample_chunk(pcm)
        pcm = ulaw_decode(ulaw_encode(pcm))
        if self._up is not None:
            pcm = self._up.resample_chunk(pcm)
        return pcm.astype(np.int16).tobytes()


# --- the whole caller side ----------------------------------------------------------------


class RawCallTrack:
    """`call_caller_raw.wav` + `call_timeline.jsonl` of one call. Never breaks a call: a
    failed write is logged once and the track stops."""

    def __init__(self, directory: Path | None, line: str) -> None:
        self._dir = directory
        self._line = line
        self._wav: wave.Wave_write | None = None
        self._timeline = None
        self._rate = 0
        self._samples = 0
        self._broken = directory is None

    @property
    def t(self) -> float:
        """Seconds of caller audio so far."""
        return round(self._samples / self._rate, 3) if self._rate else 0.0

    def audio(self, pcm: bytes, rate: int) -> None:
        if self._broken:
            return
        try:
            if self._wav is None:
                self._open(rate)
            self._wav.writeframesraw(pcm)
            self._samples += len(pcm) // 2
        except Exception:
            self._fail()

    def mark(self, kind: str, **fields) -> None:
        if self._broken or self._timeline is None:
            return
        try:
            self._timeline.write(
                json.dumps({"t": self.t, "kind": kind, **fields}, ensure_ascii=False) + "\n"
            )
            self._timeline.flush()
        except Exception:
            self._fail()

    def close(self) -> None:
        if self._timeline is not None:
            self.mark("end")
        for f in (self._wav, self._timeline):
            if f is not None:
                try:
                    f.close()
                except Exception:  # pragma: no cover
                    pass
        self._wav = self._timeline = None

    def _open(self, rate: int) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._rate = rate
        self._wav = wave.open(str(self._dir / "call_caller_raw.wav"), "wb")  # noqa: SIM115 - open for the call
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(rate)
        self._timeline = open(  # noqa: SIM115 - open for the whole call
            self._dir / "call_timeline.jsonl", "w", encoding="utf-8"
        )
        self.mark("start", epoch=round(time.time(), 3), rate=rate, line=self._line)

    def _fail(self) -> None:
        logger.warning("raw call recording failed; the call goes on without it", exc_info=True)
        self._broken = True
        self.close()


class CallerTap(FrameProcessor):
    """Right after the transport's input: every caller frame goes to the track, and the
    moments VAD heard speech and the agent spoke go to its timeline."""

    _MARKS = {
        VADUserStartedSpeakingFrame: "vad_start",
        VADUserStoppedSpeakingFrame: "vad_stop",
        BotStartedSpeakingFrame: "agent_start",
        BotStoppedSpeakingFrame: "agent_stop",
    }

    def __init__(self, track: RawCallTrack, **kwargs) -> None:
        super().__init__(**kwargs)
        self._track = track

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
            self._track.audio(frame.audio, frame.sample_rate)
        else:
            kind = self._MARKS.get(type(frame))
            if kind:
                self._track.mark(kind)
        await self.push_frame(frame, direction)
