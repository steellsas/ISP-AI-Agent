"""
Live voice demo — talk to the pipeline in your browser via FastRTC.

Step 1 of the transport work: validate the WHOLE audio loop end to end
(mic -> VAD/turn-taking -> Whisper STT -> agent -> gTTS -> speaker) with a
trivial *echo* agent, so any breakage is clearly the transport, not the real
backend. Once this feels right, swap `EchoSession` for the real `AgentSession`
(needs the LLM + tools + MCP services) — the rest of the wiring is identical.

Run (uv workspace):
    uv sync --package chatbot-core --extra voice
    uv run python chatbot_core/voice_demo.py

Then open the printed local URL, allow the microphone, and speak Lithuanian.
You should hear a greeting, then the agent repeating what it understood — which
also shows you live how well Whisper transcribes your real voice.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Standalone script: make `adapters` / `agent` importable like the tests do.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LANGUAGE = "lt"

# ASR config settled in the smoke tests: small/beam1 (~fastest) + the Lithuanian
# domain prime and VAD. Swap to "medium" here if you prefer accuracy over speed.
DOMAIN_PROMPT = (
    "Pokalbis su interneto paslaugu tiekejo klientu aptarnavimu lietuviu kalba. "
    "Klientas kalba apie interneta, rysi, greiti, gedima, saskaita ir sutarti."
)


class _Config:
    """Minimal stand-in for AgentConfig — VoicePipeline only reads `language`."""

    language = LANGUAGE


class EchoSession:
    """
    Dummy conversation matching the AgentSession seam (greeting / handle_turn /
    is_complete / config). It just echoes the transcript, so this demo exercises
    the audio path without the LLM/tools backend.
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


def main() -> None:
    from adapters.asr import FasterWhisperASR
    from adapters.transport import FastRTCVoiceTransport
    from adapters.tts import GTTSProvider
    from agent.voice_pipeline import VoicePipeline

    asr = FasterWhisperASR(
        "small",
        device="cpu",
        compute_type="int8",
        beam_size=1,
        initial_prompt=DOMAIN_PROMPT,
        vad_filter=True,
    )
    tts = GTTSProvider(default_language=LANGUAGE)
    pipeline = VoicePipeline(EchoSession(), asr, tts, language=LANGUAGE)

    transport = FastRTCVoiceTransport(pipeline)
    print("Starting voice demo — open the local URL below and allow the mic.")
    transport.start()  # launches the Gradio UI (blocks until you close it)


if __name__ == "__main__":
    main()
