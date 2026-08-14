"""
Replay bench (VOICE_PLAN V1) — re-run STT over a recorded call OFFLINE.

Feeds the saved caller WAVs (record_dir from API_RECORD_AUDIO) through a chosen
ASR backend with chosen parameters and prints the new transcript next to what
the live call heard — so STT tuning is measured, not guessed, without dialing
a call after every knob change.

Usage (from chatbot_core/):

    uv run python replay_stt.py <record_dir> [--jsonl <session.jsonl>]
        [--backend groq|local] [--model MODEL] [--prompt off|static|context]

    <record_dir>   directory with NN_user.wav files (+ manifest.jsonl)
    --jsonl        the live session's trace: supplies the ORIGINAL transcripts
                   and the per-turn dialogue context (asr events)
    --backend      groq (default; needs GROQ_API_KEY) or local faster-whisper
    --model        override the backend's model name
    --prompt       off      = no prompt at all
                   static   = domain prompt only
                   context  = domain + the live call's per-turn context (default)

Example:

    PYTHONIOENCODING=utf-8 uv run python replay_stt.py \
        logs/sessions/20260814-094244-766942-0001 \
        --jsonl logs/sessions/20260814-094244-766942-0001.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _load_live_turns(jsonl: Path | None) -> list[dict]:
    """The live call's asr events, in order (skipping too-short drops that
    produced no file is fine — files and non-empty events align by order)."""
    if not jsonl or not jsonl.exists():
        return []
    out = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "asr" and (e.get("raw") or not e.get("dropped")):
            out.append(e)
    return out


def _build_asr(backend: str, model: str | None, prompt_mode: str):
    from src.adapters.asr.lt_text import DOMAIN_PROMPT_LT

    initial = None if prompt_mode == "off" else DOMAIN_PROMPT_LT
    if backend == "local":
        from src.adapters.asr.faster_whisper_asr import FasterWhisperASR

        kwargs = {"initial_prompt": initial}
        if model:
            kwargs["model_size"] = model
        return FasterWhisperASR(**kwargs)
    from src.adapters.asr.groq_asr import GroqWhisperASR

    kwargs = {"initial_prompt": initial}
    if model:
        kwargs["model"] = model
    return GroqWhisperASR(**kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("record_dir", type=Path)
    ap.add_argument("--jsonl", type=Path, default=None)
    ap.add_argument("--backend", choices=("groq", "local"), default="groq")
    ap.add_argument("--model", default=None)
    ap.add_argument("--prompt", choices=("off", "static", "context"), default="context")
    args = ap.parse_args()

    wavs = sorted(
        args.record_dir.glob("*_user.wav"),
        key=lambda p: int(re.match(r"(\d+)", p.stem).group(1)),
    )
    if not wavs:
        print(f"no *_user.wav files in {args.record_dir}", file=sys.stderr)
        return 2

    live = _load_live_turns(args.jsonl)
    asr = _build_asr(args.backend, args.model, args.prompt)

    changed = 0
    for i, wav in enumerate(wavs):
        live_e = live[i] if i < len(live) else {}
        context = live_e.get("context") or None if args.prompt == "context" else None
        try:
            text = asr.transcribe(wav.read_bytes(), language="lt", context=context)
        except TypeError:
            text = asr.transcribe(wav.read_bytes(), language="lt")
        old = (live_e.get("raw") or "").strip()
        mark = " " if text.strip() == old else "*"
        if mark == "*":
            changed += 1
        print(f"{mark} {wav.name}")
        if old:
            print(f"    gyvai : {old}")
        print(f"    dabar : {text.strip()}")
        if context:
            print(f"    ctx   : {context[:100]}")
    print(f"\n{changed}/{len(wavs)} turn'ų transkriptas pasikeitė (* pažymėti).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
