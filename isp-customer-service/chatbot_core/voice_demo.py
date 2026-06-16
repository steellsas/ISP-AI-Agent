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
    WHISPER_MODEL=small         tiny/base/small/medium/large-v3 (bigger=accurate,slower)
    WHISPER_BEAM=1              1=fastest (greedy), 5=best quality
    WHISPER_PROMPT=1           0 disables the Lithuanian domain prime
    WHISPER_VAD=1              0 disables silence/noise trimming
    VOICE_ECHO=0               1 = echo agent (transport-only test, no LLM/tools)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Standalone script: make `adapters` / `agent` importable like the tests do.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LANGUAGE = "lt"

# Defaults are not critical — every knob is overridable per run via env.
CALLER_PHONE = os.environ.get("CALLER_PHONE", "+37060020105")
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM", "1"))
USE_PROMPT = os.environ.get("WHISPER_PROMPT", "1") != "0"
USE_VAD = os.environ.get("WHISPER_VAD", "1") != "0"
USE_ECHO = os.environ.get("VOICE_ECHO", "0") == "1"

# Primes the decoder toward Lithuanian ISP-support vocabulary + diacritics.
DOMAIN_PROMPT = (
    "Pokalbis su interneto paslaugu tiekejo klientu aptarnavimu lietuviu kalba. "
    "Klientas kalba apie interneta, rysi, greiti, gedima, saskaita ir sutarti."
)


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


def main() -> None:
    from adapters.asr import FasterWhisperASR
    from adapters.transport import FastRTCVoiceTransport
    from adapters.tts import GTTSProvider
    from agent.voice_pipeline import VoicePipeline

    print(
        f"[asr] faster-whisper '{MODEL_SIZE}' beam={BEAM_SIZE} "
        f"prompt={'on' if USE_PROMPT else 'off'} vad={'on' if USE_VAD else 'off'}"
    )
    asr = FasterWhisperASR(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8",
        beam_size=BEAM_SIZE,
        initial_prompt=DOMAIN_PROMPT if USE_PROMPT else None,
        vad_filter=USE_VAD,
    )
    tts = GTTSProvider(default_language=LANGUAGE)

    session = _build_session()
    pipeline = VoicePipeline(session, asr, tts, language=LANGUAGE)
    trace_id = getattr(session, "session_id", None)
    if trace_id:
        print(f"[trace] logs/sessions/{trace_id}.jsonl")

    transport = FastRTCVoiceTransport(pipeline)
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
