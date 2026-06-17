"""
Groq Whisper ASR adapter — hosted speech-to-text behind `ASRProvider`.

Why hosted: on a GPU-less machine local faster-whisper is either too slow
(large model: 5-11 s/turn) or too inaccurate (small model garbles addresses).
Groq runs `whisper-large-v3` on its own GPUs, giving large-model accuracy at
~1 s — breaking both walls at once. It speaks the OpenAI-compatible API, so we
reuse the already-installed `openai` SDK (no new dependency); only the base URL
and key differ.

Swap freely: this implements the exact same `transcribe` seam as the local
FasterWhisperASR. The voice pipeline and agent never change — on a GPU server
later you swap back to FasterWhisperASR(device="cuda") for full local with no
other edits (the whole point of `ports.asr`).
"""

from __future__ import annotations

import io
import logging
import os
import wave
from typing import Any

logger = logging.getLogger(__name__)

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqWhisperASR:
    """Hosted `ASRProvider` backed by Groq's whisper-large-v3."""

    def __init__(
        self,
        model: str = "whisper-large-v3",
        *,
        default_language: str | None = "lt",
        api_key: str | None = None,
        initial_prompt: str | None = None,
        base_url: str = _GROQ_BASE_URL,
    ):
        """
        Args:
            model: Groq transcription model ("whisper-large-v3" or the faster
                "whisper-large-v3-turbo").
            default_language: ISO hint when transcribe(language=None).
            api_key: Groq key; defaults to the GROQ_API_KEY env var.
            initial_prompt: biases spelling toward the domain (same idea as the
                local adapter's prompt) — passed as the API `prompt`.
            base_url: OpenAI-compatible endpoint (Groq by default).
        """
        self._model = model
        self._default_language = default_language
        self._api_key = api_key
        self._initial_prompt = initial_prompt
        self._base_url = base_url
        self._client: Any | None = None  # lazy OpenAI client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # already installed; no extra dep

            key = self._api_key or os.getenv("GROQ_API_KEY")
            if not key:
                raise RuntimeError("GROQ_API_KEY is not set — needed for Groq speech-to-text.")
            self._client = OpenAI(api_key=key, base_url=self._base_url)
        return self._client

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        sample_rate: int = 16_000,
    ) -> str:
        """Return the recognised text for `audio` (WAV or raw 16-bit PCM)."""
        if not audio:
            return ""

        wav = self._to_wav_bytes(audio, sample_rate)
        client = self._ensure_client()
        resp = client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", wav, "audio/wav"),
            language=language or self._default_language,
            prompt=self._initial_prompt or None,
            response_format="text",
        )
        text = resp if isinstance(resp, str) else getattr(resp, "text", "")
        logger.debug("Groq ASR transcript (%d chars): %s", len(text), text)
        return text.strip()

    @staticmethod
    def _to_wav_bytes(audio: bytes, sample_rate: int) -> bytes:
        """
        Wrap raw int16 mono PCM in a WAV container (Groq wants an audio file).

        A WAV input (RIFF header) is passed through unchanged — it already
        carries its own sample rate; Whisper resamples server-side.
        """
        if audio[:4] == b"RIFF":
            return audio
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(audio)
        return buffer.getvalue()
