"""
Manual voice smoke test — exercises the REAL engines, not a pytest test.

This is the first step of the Phase 3 voice work: before wiring FastRTC, we
prove the heavy/fragile parts work on *this* machine in isolation —
faster-whisper (ctranslate2) loads, the `medium` model downloads, gTTS reaches
Google, and Whisper actually understands Lithuanian. Every transcription goes
through the real `FasterWhisperASR` adapter (the exact path FastRTC will use),
so anything that breaks here would break the transport too.

It needs the optional `voice` extra (downloads ~1.5 GB on first run) and network
access (gTTS), so it lives outside the offline pytest suite.

Run (uv workspace):
    uv sync --package chatbot-core --extra voice
    uv run python chatbot_core/smoke_voice.py
    # ...and with YOUR OWN voice (any format: wav / mp3 / m4a):
    uv run python chatbot_core/smoke_voice.py path\\to\\your_recording.wav

What to expect:
    - First run is slow: it downloads the `medium` weights, then loads them.
    - On CPU, transcription of a short clip is typically a few seconds.
    - The gTTS round-trip (synthetic voice) is an *easy* case — real human
      speech via the file argument is the honest "how does it understand" test.
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

# Standalone script: make `adapters` / `agent` importable like the tests do.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Whisper config for this smoke test — chosen per the CPU-only decision.
# Override per run to A/B latency vs accuracy without editing the file:
#   set WHISPER_MODEL=small   (tiny/base/small/medium/large-v3)
#   set WHISPER_BEAM=1        (1 = greedy/fastest, 5 = best quality)
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "medium")
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM", "5"))
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
LANGUAGE = "lt"

# Accuracy levers for real (noisy) voice. Toggle to A/B their effect:
#   set WHISPER_PROMPT=0   -> disable the domain prime
#   set WHISPER_VAD=0      -> disable silence/noise trimming
USE_PROMPT = os.environ.get("WHISPER_PROMPT", "1") != "0"
USE_VAD = os.environ.get("WHISPER_VAD", "1") != "0"

# Shared domain prime (names the demo's cities/streets so Whisper spells them).
from adapters.asr import DOMAIN_PROMPT_LT as DOMAIN_PROMPT  # noqa: E402

# ISP-domain Lithuanian sentences — exercise the vocabulary the agent will hear.
SENTENCES = [
    "Laba diena, man neveikia internetas namuose.",
    "Mano interneto greitis labai letas vakarais.",
    "Noreciau patikrinti savo saskaitos likuti.",
]


def _check_deps() -> None:
    """Fail early with a friendly hint if the `voice` extra isn't installed."""
    missing = []
    for mod in ("faster_whisper", "gtts"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"[X] Missing voice dependencies: {', '.join(missing)}")
        print("    Install them with:")
        print("    uv sync --package chatbot-core --extra voice")
        sys.exit(1)


def _decode_to_pcm16(source: bytes | str) -> bytes:
    """
    Decode any audio (bytes or file path, any container) to raw 16-bit PCM
    mono @ 16 kHz — the byte form our ASR adapter consumes.

    Uses faster-whisper's own decoder (PyAV under the hood), so wav/mp3/m4a all
    work without us hand-rolling format handling.
    """
    import numpy as np

    try:
        from faster_whisper import decode_audio
    except ImportError:  # older layouts expose it under .audio
        from faster_whisper.audio import decode_audio

    data = io.BytesIO(source) if isinstance(source, bytes) else source
    samples = decode_audio(data, sampling_rate=16_000)  # float32 in [-1, 1]
    pcm = (np.asarray(samples) * 32768.0).clip(-32768, 32767).astype("<i2")
    return pcm.tobytes()


def _tts_demo() -> list[tuple[str, bytes]]:
    """Synthesize each sentence with the real gTTS adapter; save MP3s to listen."""
    from adapters.tts import GTTSProvider

    print("\n=== TTS (gTTS) ===")
    tts = GTTSProvider(default_language=LANGUAGE)
    out = []
    for i, text in enumerate(SENTENCES, start=1):
        t0 = time.perf_counter()
        audio = tts.synthesize(text, language=LANGUAGE)
        dt = time.perf_counter() - t0
        path = Path(__file__).parent / f"smoke_tts_{i}.mp3"
        path.write_bytes(audio)
        print(f"  [{i}] {len(audio):>6} bytes in {dt:4.1f}s -> {path.name}  ({text!r})")
        out.append((text, audio))
    print("  (play the .mp3 files to judge the Lithuanian TTS voice)")
    return out


def _asr_roundtrip(samples: list[tuple[str, bytes]]) -> None:
    """Feed the gTTS audio back through the real ASR adapter and compare."""
    from adapters.asr import FasterWhisperASR

    print(
        f"\n=== ASR (faster-whisper '{MODEL_SIZE}', {DEVICE}/{COMPUTE_TYPE}, beam={BEAM_SIZE}) ==="
    )
    print(f"  prompt={'on' if USE_PROMPT else 'off'}  vad={'on' if USE_VAD else 'off'}")
    print("  Loading model (first run downloads weights)...")
    asr = FasterWhisperASR(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        beam_size=BEAM_SIZE,
        initial_prompt=DOMAIN_PROMPT if USE_PROMPT else None,
        vad_filter=USE_VAD,
    )

    print("  Round-trip (synthetic voice — the easy case):")
    for i, (expected, mp3) in enumerate(samples, start=1):
        pcm = _decode_to_pcm16(mp3)
        t0 = time.perf_counter()
        heard = asr.transcribe(pcm, language=LANGUAGE, sample_rate=16_000)
        dt = time.perf_counter() - t0
        # First call includes model load; later calls show steady-state latency.
        print(f"  [{i}] {dt:5.1f}s  expected: {expected!r}")
        print(f"           heard:    {heard!r}")


def _asr_file(path: str) -> None:
    """Transcribe a real recording (your own voice) through the ASR adapter."""
    from adapters.asr import FasterWhisperASR

    print(f"\n=== ASR on your recording: {path} ===")
    print(
        f"  model='{MODEL_SIZE}' beam={BEAM_SIZE} ({DEVICE}/{COMPUTE_TYPE}) "
        f"prompt={'on' if USE_PROMPT else 'off'} vad={'on' if USE_VAD else 'off'}"
    )
    pcm = _decode_to_pcm16(path)
    asr = FasterWhisperASR(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        beam_size=BEAM_SIZE,
        initial_prompt=DOMAIN_PROMPT if USE_PROMPT else None,
        vad_filter=USE_VAD,
    )
    t0 = time.perf_counter()
    heard = asr.transcribe(pcm, language=LANGUAGE, sample_rate=16_000)
    dt = time.perf_counter() - t0
    print(f"  ({dt:.1f}s)  heard:      {heard!r}")
    # Show the number-normalized form the agent would actually receive.
    from adapters.asr import normalize_lt_numbers

    print(f"           normalized: {normalize_lt_numbers(heard)!r}")


def main() -> None:
    _check_deps()

    user_file = sys.argv[1] if len(sys.argv) > 1 else None
    if user_file:
        # Real-voice mode: skip the synthetic round-trip, go straight to truth.
        _asr_file(user_file)
    else:
        samples = _tts_demo()
        _asr_roundtrip(samples)

    print("\nDone. If this looked sane, FastRTC is just wiring on top of these.")


if __name__ == "__main__":
    main()
