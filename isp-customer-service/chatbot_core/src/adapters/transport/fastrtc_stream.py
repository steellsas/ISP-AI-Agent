"""
FastRTC transport — a WebRTC voice channel in front of the `VoicePipeline`.

This is the *wire* for the voice slice: it owns the live audio connection (mic
in / speaker out via WebRTC) and nothing about dialog logic. FastRTC's
`ReplyOnPause` does turn-taking (Silero VAD) — it buffers the caller's speech
and fires our reply function once they pause. We bridge its numpy audio frames
to the byte form the pipeline speaks, run one `VoiceTurn`, and stream the
synthesized reply back.

Why this lives behind the `Transport` port: the exact same `VoicePipeline`
(ASR -> AgentSession -> TTS) serves this FastRTC web demo today and a Twilio/PBX
telephony adapter later — only this file changes. The agent core never learns
what a WebRTC frame is.

The `fastrtc` and `av` imports are deferred so this module imports without the
optional `voice` extra installed (the audio-conversion helpers stay unit-
testable offline); only `start()` needs the engine.
"""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from agent.voice_pipeline import VoicePipeline

logger = logging.getLogger(__name__)

# TTS playback rate handed to FastRTC; it resamples to the WebRTC 48 kHz wire.
_DEFAULT_OUTPUT_RATE = 24_000


class FastRTCVoiceTransport:
    """`Transport` that serves the pipeline over WebRTC with a built-in UI."""

    def __init__(
        self,
        pipeline: VoicePipeline,
        *,
        output_sample_rate: int = _DEFAULT_OUTPUT_RATE,
        record_dir: str | Path | None = None,
        started_talking_threshold: float = 0.3,
        speech_threshold: float = 0.3,
        audio_chunk_duration: float = 0.6,
        can_interrupt: bool = False,
        play_filler: bool = False,
        stream_playback: bool = True,
        **launch_kwargs: Any,
    ):
        """
        Args:
            pipeline: The audio-in/audio-out conversation pipeline to serve.
            output_sample_rate: Sample rate we tag synthesized reply audio with.
            record_dir: if set, save each turn's audio (caller WAV + agent reply)
                here, so a real call can be replayed and re-tested offline.
            started_talking_threshold: seconds of speech in a chunk before a turn
                starts (FastRTC default 0.2 fires on brief noise; 0.3 is calmer).
            speech_threshold: pause length (s) that ends the caller's turn
                (default 0.1 cuts people off mid-sentence; 0.3 lets them breathe).
            audio_chunk_duration: VAD processing chunk size (s).
            can_interrupt: barge-in. FastRTC defaults this to True, but without
                acoustic echo cancellation the agent's own voice (and room noise)
                re-triggers the VAD and CUTS THE AGENT OFF mid-sentence. Default
                False here so the agent always finishes speaking; re-enable once
                echo cancellation is in place.
            **launch_kwargs: Forwarded to `Stream.ui.launch()` (e.g. `share=True`,
                `server_port=...`).
        """
        self._pipeline = pipeline
        self._output_sample_rate = output_sample_rate
        self._record_dir = Path(record_dir) if record_dir else None
        self._started_talking_threshold = started_talking_threshold
        self._speech_threshold = speech_threshold
        self._audio_chunk_duration = audio_chunk_duration
        self._can_interrupt = can_interrupt
        self._play_filler = play_filler
        self._stream_playback = stream_playback
        self._turn_idx = 0
        self._launch_kwargs = launch_kwargs
        self._stream: Any | None = None
        if self._record_dir is not None:
            self._record_dir.mkdir(parents=True, exist_ok=True)

    # --- Transport port ----------------------------------------------------

    def start(self) -> None:
        """Open the channel and launch the Gradio test UI (blocks)."""
        if self._stream is None:
            self._stream = self._build_stream()
        logger.info("Launching FastRTC voice UI...")
        self._stream.ui.launch(**self._launch_kwargs)

    def stop(self) -> None:
        """Close the UI / release the channel."""
        if self._stream is not None:
            try:
                self._stream.ui.close()
            except Exception:  # best-effort; UI may already be down
                logger.debug("FastRTC UI close failed", exc_info=True)

    # --- FastRTC wiring -----------------------------------------------------

    def _build_stream(self) -> Any:
        from fastrtc import AlgoOptions, ReplyOnPause, Stream  # deferred (optional dep)

        # Calmer turn-taking than the defaults: needs a bit more speech to start
        # (fewer noise false-fires) and waits a touch longer before replying
        # (stops cutting the caller off mid-sentence).
        algo = AlgoOptions(
            audio_chunk_duration=self._audio_chunk_duration,
            started_talking_threshold=self._started_talking_threshold,
            speech_threshold=self._speech_threshold,
        )
        handler = ReplyOnPause(
            self._reply,
            startup_fn=self._startup,
            algo_options=algo,
            can_interrupt=self._can_interrupt,
        )
        return Stream(handler=handler, modality="audio", mode="send-receive")

    def _startup(self):
        """Speak the greeting once, before the caller says anything."""
        audio = self._pipeline.greeting_audio()
        self._save_audio("00_agent", audio, kind="reply")
        out = self._decode_audio_to_int16(audio, self._output_sample_rate)
        if out.size:
            yield (self._output_sample_rate, out)

    def _reply(self, audio: tuple[int, Any]):
        """Run one full voice turn for a detected utterance and stream it back."""
        pcm, sample_rate = self._incoming_to_pcm16(audio)
        self._turn_idx += 1
        self._save_audio(f"{self._turn_idx:02d}_user", pcm, kind="pcm", sample_rate=sample_rate)

        # Instant filler (step 2.2): play a cached "let me check" cue immediately so
        # the caller hears the agent working while ASR+agent+TTS compute. Best-
        # effort; a synth/decode failure must never block the real reply.
        if self._play_filler:
            filler = getattr(self._pipeline, "filler_audio", None)
            if callable(filler):
                try:
                    fout = self._decode_audio_to_int16(filler(), self._output_sample_rate)
                    if fout.size:
                        yield (self._output_sample_rate, fout)
                except Exception:  # pragma: no cover - best-effort
                    logger.debug("Filler playback failed", exc_info=True)

        # Streaming playback (C2b): play each sentence's audio as soon as it is
        # synthesized, so the agent starts speaking before the whole reply is
        # rendered. Falls back to the one-blob path if the pipeline can't stream.
        if self._stream_playback and hasattr(self._pipeline, "stream_turn"):
            saved = bytearray()
            for chunk in self._pipeline.stream_turn(pcm, sample_rate=sample_rate):
                saved += chunk
                out = self._decode_audio_to_int16(chunk, self._output_sample_rate)
                if out.size:
                    yield (self._output_sample_rate, out)
            if saved:
                self._save_audio(f"{self._turn_idx:02d}_agent", bytes(saved), kind="reply")
            return

        turn = self._pipeline.handle_audio(pcm, sample_rate=sample_rate)
        self._save_audio(f"{self._turn_idx:02d}_agent", turn.reply_audio, kind="reply")
        # Latency breakdown is the raw material for the masking decision (a vs b).
        logger.info(
            "voice turn | heard=%r -> reply=%r | asr=%.0fms agent=%.0fms tts=%.0fms total=%.0fms",
            turn.transcript,
            turn.reply_text,
            turn.asr_ms,
            turn.agent_ms,
            turn.tts_ms,
            turn.asr_ms + turn.agent_ms + turn.tts_ms,
        )
        out = self._decode_audio_to_int16(turn.reply_audio, self._output_sample_rate)
        if out.size:
            yield (self._output_sample_rate, out)

    # --- Audio recording (opt-in: replay & offline re-test) ----------------

    def _save_audio(self, stem: str, data: bytes, *, kind: str, sample_rate: int = 16_000):
        """Save one turn's audio: caller PCM -> WAV, agent reply bytes -> as-is."""
        if self._record_dir is None or not data:
            return
        try:
            if kind == "pcm":
                path = self._record_dir / f"{stem}.wav"
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(sample_rate)
                    wav.writeframes(data)
            else:
                # gTTS emits MP3. Detect MP3 (ID3 tag or any MPEG frame sync
                # 0xFFEx — gTTS uses 0xFFF3 too, not only 0xFFFB) / WAV; else
                # default to .mp3 since the TTS is gTTS.
                if data[:4] == b"RIFF":
                    ext = "wav"
                elif data[:3] == b"ID3" or (
                    len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
                ):
                    ext = "mp3"
                else:
                    ext = "mp3"
                (self._record_dir / f"{stem}.{ext}").write_bytes(data)
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning(f"Audio record failed ({stem}): {e}")

    # --- Audio bridging (pure, offline-testable) ---------------------------

    @staticmethod
    def _incoming_to_pcm16(audio: tuple[int, Any]) -> tuple[bytes, int]:
        """
        FastRTC frame -> (raw int16 mono PCM bytes, sample_rate) for the ASR.

        FastRTC delivers `(sample_rate, ndarray)` shaped `(1, N)`, dtype int16
        or float32. We flatten to mono and coerce to int16 — exactly what
        `ASRProvider.transcribe` accepts as raw PCM.
        """
        sample_rate, arr = audio
        arr = np.asarray(arr)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        if arr.dtype != np.int16:
            arr = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
        return arr.tobytes(), int(sample_rate)

    @staticmethod
    def _decode_audio_to_int16(data: bytes, target_rate: int) -> Any:
        """
        Decode TTS bytes (gTTS MP3, or WAV) -> int16 mono ndarray `(1, N)` at
        `target_rate`, the shape FastRTC streams back to the browser.

        Uses PyAV (`av`, pulled in by the voice extra) so any container the TTS
        backend emits decodes the same way — when we later swap gTTS for a PCM
        engine like Piper, this still works unchanged.
        """
        if not data:
            return np.zeros((1, 0), dtype=np.int16)

        import av  # deferred (optional dep)

        chunks: list[Any] = []
        with av.open(io.BytesIO(data)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=target_rate)
            for frame in container.decode(audio=0):
                chunks.extend(_resample(resampler, frame))
            chunks.extend(_resample(resampler, None))  # flush the resampler tail

        if not chunks:
            return np.zeros((1, 0), dtype=np.int16)
        out = np.concatenate(chunks, axis=1)
        return out.astype(np.int16) if out.dtype != np.int16 else out


def _resample(resampler: Any, frame: Any) -> list[Any]:
    """Normalize PyAV's resampler output (list in new versions, frame in old)."""
    res = resampler.resample(frame)
    if res is None:
        return []
    frames = res if isinstance(res, list) else [res]
    return [f.to_ndarray() for f in frames]
