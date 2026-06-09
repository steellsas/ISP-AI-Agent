"""
Live voice demo — talk to the REAL agent in your browser via FastRTC.

Step 2 of the transport work. `voice_demo.py` proved the audio loop with a
trivial echo; this swaps `EchoSession` for the real `AgentSession` (LLM + tools
+ RAG + the CRM / network-diagnostic services), so you have the FULL voice
conversation: mic -> VAD -> Whisper STT -> agent (looks the caller up, runs
diagnostics) -> gTTS -> speaker. The transport wiring is byte-for-byte the same
as the echo demo — only the session object changes. That is the whole point of
the `AgentSession` seam: transports don't know whether they're driving an echo
or the production brain.

Who is calling: a phone number identifies the customer (in real telephony it
comes from the call; here we set it). It defaults to a seeded customer with a
known fault so the agent has something real to diagnose. Override per run:
    set VOICE_CALLER_PHONE=+37060012352   (CUST008 — intermittent / packet loss)

Run (uv workspace):
    uv sync --package chatbot-core --extra voice
    uv run python chatbot_core/voice_agent_demo.py

Then open the printed local URL, allow the microphone, and speak Lithuanian.
You should hear the agent's real greeting; describe your problem and it will
reason + call tools just like the Streamlit demo, but by voice.

Needs OPENAI_API_KEY (loaded from the repo-root .env below) for the LLM.
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

# Default caller — a seeded customer with a real fault so the agent has
# something to diagnose. CUST002: area outage on Dainų g. (Šiauliai).
# Override with VOICE_CALLER_PHONE to test other seeded scenarios.
DEFAULT_CALLER_PHONE = "+37060012346"

# ASR config settled in the smoke tests: small/beam1 (~fastest) + the Lithuanian
# domain prime and VAD. Swap to "medium" here if you prefer accuracy over speed.
DOMAIN_PROMPT = (
    "Pokalbis su interneto paslaugu tiekejo klientu aptarnavimu lietuviu kalba. "
    "Klientas kalba apie interneta, rysi, greiti, gedima, saskaita ir sutarti."
)


def main() -> None:
    # Load the repo-root .env (OPENAI_API_KEY etc.) and set up session logging
    # before anything reads/logs. Entry-point scripts are the right place for
    # this — the framework-free core stays clean. We reuse the SAME shared
    # helpers the text CLI uses, so a voice session produces an identical,
    # reviewable log (full transcript, tool calls, per-stage timings).
    from utils import load_env, setup_session_logging

    load_env(Path(__file__).resolve().parent.parent / ".env")  # isp-customer-service/.env
    log_file, _ = setup_session_logging("voice_session")
    print(f"📝 Visa sesija rašoma į: {log_file}")

    if not os.environ.get("OPENAI_API_KEY"):
        print("[X] OPENAI_API_KEY not set (checked the environment and repo-root .env).")
        print("    Put it in isp-customer-service/.env or `set OPENAI_API_KEY=...` first.")
        sys.exit(1)

    from adapters.asr import FasterWhisperASR
    from adapters.transport import FastRTCVoiceTransport
    from adapters.tts import GTTSProvider
    from agent.session import AgentSession
    from agent.voice_pipeline import VoicePipeline

    caller_phone = os.environ.get("VOICE_CALLER_PHONE", DEFAULT_CALLER_PHONE)

    asr = FasterWhisperASR(
        "small",
        device="cpu",
        compute_type="int8",
        beam_size=1,
        initial_prompt=DOMAIN_PROMPT,
        vad_filter=True,
    )
    tts = GTTSProvider(default_language=LANGUAGE)
    # The real brain — same seam EchoSession imitated (greeting / handle_turn /
    # is_complete / config), so the pipeline and transport below are unchanged.
    session = AgentSession(caller_phone=caller_phone, language=LANGUAGE)
    pipeline = VoicePipeline(session, asr, tts, language=LANGUAGE)

    transport = FastRTCVoiceTransport(pipeline)
    print(f"Starting voice AGENT demo (caller={caller_phone}).")
    print("Open the local URL below, allow the mic, and speak Lithuanian.")
    transport.start()  # launches the Gradio UI (blocks until you close it)


if __name__ == "__main__":
    main()
