"""
faster-whisper ASR adapter — local speech-to-text behind `ASRProvider`.

Why local: no per-call cost, audio never leaves the machine (GDPR), and good
Lithuanian quality. The engine (ctranslate2 `WhisperModel`) and its model
weights are heavyweight, so both the import and the model load are **lazy** —
constructing this adapter is cheap (no download, no import), which lets the
Protocol-conformance tests run without the optional `voice` dependency
installed. The weights download on the first `transcribe` call only.

Swap freely: a hosted Whisper API adapter can implement the same `transcribe`
seam without touching the agent core (that's the whole point of `ports.asr`).
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Any

logger = logging.getLogger(__name__)

# Whisper models operate at 16 kHz mono.
_WHISPER_SAMPLE_RATE = 16_000


class FasterWhisperASR:
    """Local `ASRProvider` backed by faster-whisper (ctranslate2)."""

    def __init__(
        self,
        model_size: str = "small",
        *,
        device: str = "auto",
        compute_type: str = "int8",
        default_language: str | None = "lt",
        download_root: str | None = None,
        beam_size: int = 5,
        initial_prompt: str | None = None,
        vad_filter: bool = False,
    ):
        """
        Configure the adapter (no model is loaded yet).

        Args:
            model_size: faster-whisper model id ("tiny"/"base"/"small"/"medium"/
                "large-v3"). Bigger = better LT, slower, larger download.
            device: "auto" | "cpu" | "cuda".
            compute_type: ctranslate2 compute type ("int8" is a good CPU default).
            default_language: ISO hint used when `transcribe(language=None)`.
            download_root: where to cache model weights (None = library default).
            beam_size: decoding beam width. 5 = best quality; 1 (greedy) is the
                main CPU-latency lever, trading a little accuracy for ~2x speed.
            initial_prompt: text primed into the decoder to bias vocabulary and
                spelling toward the domain (e.g. a short Lithuanian ISP-support
                sentence). The single most effective lever for real-voice domain
                terms and diacritics — it costs nothing at runtime.
            vad_filter: run Silero VAD first to drop silence/noise before/after
                speech. Reduces hallucination on real recordings.
        """
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._default_language = default_language
        self._download_root = download_root
        self._beam_size = beam_size
        self._initial_prompt = initial_prompt
        self._vad_filter = vad_filter
        self._model: Any | None = None  # lazy WhisperModel

    def _ensure_model(self) -> Any:
        """Load (and cache) the WhisperModel on first use."""
        if self._model is None:
            from faster_whisper import WhisperModel  # heavy import, deferred

            logger.info(
                "Loading faster-whisper model '%s' (device=%s, compute=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._download_root,
            )
        return self._model

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        sample_rate: int = _WHISPER_SAMPLE_RATE,
        context: str | None = None,
    ) -> str:
        """
        Return the recognised text for `audio`.

        `audio` is either a WAV container (RIFF header) or raw little-endian
        16-bit PCM. WAV carries its own sample rate; raw PCM uses `sample_rate`.
        Both are normalised to mono float32 @ 16 kHz for the model.
        `context` (VOICE_PLAN V1): per-turn dialogue biasing appended to the
        static domain prompt.
        """

        samples = self._to_float32_mono(audio, sample_rate)
        if samples.size == 0:
            return ""

        from .lt_text import compose_prompt

        model = self._ensure_model()
        segments, _info = model.transcribe(
            samples,
            language=language or self._default_language,
            beam_size=self._beam_size,
            initial_prompt=compose_prompt(self._initial_prompt, context) or None,
            vad_filter=self._vad_filter,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        logger.debug("ASR transcript (%d chars): %s", len(text), text)
        return text

    @staticmethod
    def _to_float32_mono(audio: bytes, sample_rate: int) -> Any:
        """
        Decode `audio` bytes to a mono float32 numpy array in [-1, 1] at 16 kHz.

        Accepts a WAV container (parsed via the stdlib `wave` module — no extra
        dependency) or raw int16 PCM. Resamples to 16 kHz with linear
        interpolation when needed (good enough for speech ASR).
        """
        import numpy as np

        if audio[:4] == b"RIFF":
            with wave.open(io.BytesIO(audio), "rb") as wav:
                channels = wav.getnchannels()
                width = wav.getsampwidth()
                src_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
            if width != 2:
                raise ValueError(f"Unsupported WAV sample width: {width * 8}-bit (need 16-bit)")
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)
        else:
            # Raw little-endian 16-bit PCM, assumed mono at the given rate.
            data = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
            src_rate = sample_rate

        if src_rate != _WHISPER_SAMPLE_RATE and data.size:
            duration = data.size / float(src_rate)
            target_len = int(round(duration * _WHISPER_SAMPLE_RATE))
            if target_len > 0:
                xp = np.linspace(0.0, 1.0, num=data.size, endpoint=False)
                x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
                data = np.interp(x, xp, data).astype(np.float32)

        return data
