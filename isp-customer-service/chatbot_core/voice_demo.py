"""
Live voice demo — talk to the real agent in your browser via FastRTC.

Step B of the voice work: the FULL backend over voice
(mic -> VAD/turn-taking -> Whisper STT -> AgentSession -> gTTS -> speaker).
Every turn is written to logs/sessions/<id>.jsonl (the conversation trace) —
that file is how you debug a voice call, since you cannot read it live.

Run (uv workspace):
    uv sync --package chatbot-core --extra voice
    uv run python scripts/setup_db.py && uv run python scripts/seed_data.py
    set CALLER_PHONE=+37060020105      # who is calling (phone-first identification)
    uv run python chatbot_core/voice_demo.py

Then open the printed local URL, allow the microphone, and speak Lithuanian.
See chatbot_core/docs/balso_testavimo_scenarijai.md for what to say.

Tunables (env, no file edit needed):
    CALLER_PHONE=+37060020105   caller number (default below; any seed phone)
    ASR_BACKEND=groq            groq (hosted, fast+accurate) | local (faster-whisper CPU)
    TTS_ENGINE=edge             edge (free neural LT, streaming) | gtts
    TTS_VOICE=lt-LT-LeonasNeural edge voice (male; lt-LT-OnaNeural = female)
    GROQ_API_KEY=...            required when ASR_BACKEND=groq
    GROQ_MODEL=whisper-large-v3 whisper-large-v3 | whisper-large-v3-turbo
    WHISPER_MODEL=small         (local only) tiny/base/small/medium/large-v3
    WHISPER_BEAM=1              (local only) 1=fastest, 5=best quality
    WHISPER_PROMPT=1           0 disables the Lithuanian domain prime
    WHISPER_VAD=1              (local only) 0 disables silence/noise trimming
    VOICE_ECHO=0               1 = echo agent (transport-only test, no LLM/tools)
    VOICE_BARGE_IN=0           1 = let the caller interrupt the agent (needs echo
                               cancellation; default off so the agent finishes)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Standalone script: make `adapters` / `agent` importable like the tests do.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load the project .env so keys (GROQ_API_KEY, OPENAI_API_KEY) need not be set
# in the shell — the adapters read them straight from os.environ. OS-level env
# vars still win / work if no .env is present.
try:
    from utils import load_env

    load_env()
except Exception:  # .env is optional; OS environment is the fallback
    pass

LANGUAGE = "lt"

# Defaults are not critical — every knob is overridable per run via env.
CALLER_PHONE = os.environ.get("CALLER_PHONE", "+37060020105")
ASR_BACKEND = os.environ.get("ASR_BACKEND", "groq").lower()  # groq | local
TTS_ENGINE = os.environ.get("TTS_ENGINE", "edge").lower()  # edge (neural) | gtts
GROQ_MODEL = os.environ.get("GROQ_MODEL", "whisper-large-v3")
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM", "1"))
USE_PROMPT = os.environ.get("WHISPER_PROMPT", "1") != "0"
USE_VAD = os.environ.get("WHISPER_VAD", "1") != "0"
USE_ECHO = os.environ.get("VOICE_ECHO", "0") == "1"
RECORD_AUDIO = os.environ.get("RECORD_AUDIO", "0") == "1"


class _Config:
    """Minimal stand-in for AgentConfig (echo mode only reads `language`)."""

    language = LANGUAGE


class EchoSession:
    """
    Transport-only test double matching the AgentSession seam. Echoes the
    transcript, so VOICE_ECHO=1 exercises the audio path with no LLM/tools.
    """

    def __init__(self):
        self.config = _Config()
        self.is_complete = False

    def greeting(self) -> str:
        return "Laba diena! Cia balso demo. Pasakykite ka nors, ir as pakartosiu."

    def handle_turn(self, text: str) -> str:
        if not text.strip():
            return "Atsiprasau, nieko negirdejau. Pakartokite, prasau."
        return f"Jus pasakete: {text}"

    def end_session(self, outcome: str | None = None) -> None:
        return None


def _build_session():
    """The real AgentSession (LLM + tools + trace), or the echo double."""
    if USE_ECHO:
        print("[mode] ECHO — transport only, no LLM/tools.")
        return EchoSession()
    from agent.session import AgentSession

    print(f"[mode] REAL agent — caller={CALLER_PHONE}")
    return AgentSession(caller_phone=CALLER_PHONE, language=LANGUAGE)


def _build_asr():
    """Hosted Groq STT (fast+accurate, needs GROQ_API_KEY) or local CPU Whisper."""
    from adapters.asr import DOMAIN_PROMPT_LT

    prompt = DOMAIN_PROMPT_LT if USE_PROMPT else None
    if ASR_BACKEND == "groq":
        from adapters.asr import GroqWhisperASR

        print(f"[asr] Groq '{GROQ_MODEL}' (hosted) prompt={'on' if USE_PROMPT else 'off'}")
        return GroqWhisperASR(GROQ_MODEL, default_language=LANGUAGE, initial_prompt=prompt)

    from adapters.asr import FasterWhisperASR

    print(
        f"[asr] faster-whisper '{MODEL_SIZE}' beam={BEAM_SIZE} (local CPU) "
        f"prompt={'on' if USE_PROMPT else 'off'} vad={'on' if USE_VAD else 'off'}"
    )
    return FasterWhisperASR(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8",
        beam_size=BEAM_SIZE,
        initial_prompt=prompt,
        vad_filter=USE_VAD,
    )


def _build_tts():
    """Edge neural LT voice (default, streaming-capable) or gTTS."""
    if TTS_ENGINE == "gtts":
        from adapters.tts import GTTSProvider

        print("[tts] gTTS (Google) — LT")
        return GTTSProvider(default_language=LANGUAGE)

    from adapters.tts import EdgeTTSProvider

    voice = os.environ.get("TTS_VOICE", "lt-LT-LeonasNeural")
    print(f"[tts] edge-tts (neural) — {voice}")
    return EdgeTTSProvider(default_language=LANGUAGE, voice=voice)


def main() -> None:
    from adapters.asr import is_asr_noise, normalize_lt_numbers
    from adapters.transport import FastRTCVoiceTransport
    from agent.voice_pipeline import VoicePipeline

    asr = _build_asr()
    tts = _build_tts()

    session = _build_session()
    # transcript_filter: spoken-number -> digit cleanup before the agent.
    # noise_filter: drop silence/noise hallucinations ("www.youtube.com").
    pipeline = VoicePipeline(
        session,
        asr,
        tts,
        language=LANGUAGE,
        transcript_filter=normalize_lt_numbers,
        noise_filter=is_asr_noise,
    )
    trace_id = getattr(session, "session_id", None)
    if trace_id:
        print(f"[trace] logs/sessions/{trace_id}.jsonl  (+ .txt on exit)")

    record_dir = None
    if RECORD_AUDIO and trace_id:
        record_dir = Path(__file__).resolve().parent.parent / "logs" / "sessions" / trace_id
        print(f"[record] per-turn audio -> {record_dir}")

    # VAD turn-taking (env-tunable): calmer than FastRTC defaults.
    transport = FastRTCVoiceTransport(
        pipeline,
        record_dir=record_dir,
        started_talking_threshold=float(os.environ.get("VAD_STARTED", "0.3")),
        speech_threshold=float(os.environ.get("VAD_SPEECH", "0.3")),
        audio_chunk_duration=float(os.environ.get("VAD_CHUNK", "0.6")),
        # Barge-in OFF by default: without echo cancellation the agent's own
        # voice cuts it off mid-sentence. VOICE_BARGE_IN=1 to re-enable.
        can_interrupt=os.environ.get("VOICE_BARGE_IN", "0") == "1",
        # Instant filler OFF by default: a fixed "tikrinu…" cue felt robotic; the
        # real masking is streaming (Pillar C). VOICE_FILLER=1 to experiment.
        play_filler=os.environ.get("VOICE_FILLER", "0") == "1",
        # Streaming playback ON: speak each sentence as it is synthesized.
        # STREAM_PLAYBACK=0 to fall back to one-blob playback.
        stream_playback=os.environ.get("STREAM_PLAYBACK", "1") != "0",
    )
    print("Starting voice demo — open the local URL below and allow the mic.")
    try:
        transport.start()  # launches the Gradio UI (blocks until you close it)
    finally:
        # Close the conversation trace when the UI is shut down.
        end = getattr(session, "end_session", None)
        if callable(end):
            end(outcome="voice_demo_end")


if __name__ == "__main__":
    main()
