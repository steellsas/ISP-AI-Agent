"""What a call ran on — the code, the knowledge, the prompts and the models (ROADMAP 3.1).

Every call's trace starts with these, so a call made after a change can be compared with one
made before it: the same scenario, a different card or prompt, and the result shows which.
The file hashes are computed per call (about 140 small files, a few ms): the instructor's
edits reach new calls without a restart, and the tag must say so.
"""

from __future__ import annotations

import functools
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

_AGENT = Path(__file__).resolve().parent
_SRC = _AGENT.parent

# What each hash covers: the parts an instructor or an AI engineer changes between calls.
CONTENT = {
    "knowledge": [_AGENT / "knowledge"],  # cards, modules, equipment, policies, limits, tools
    "locale": [_AGENT / "locales"],  # phrases, vocabulary, examples
    "prompts": [_AGENT / "prompts"],
    "documents": [_SRC / "rag" / "knowledge_base"],  # what the agent may read to the caller
}


@functools.lru_cache(maxsize=1)
def code_version() -> str:
    """The git commit the process started on; `+changes` when files were edited but not
    committed (a development run). `unknown` outside a git checkout."""
    try:

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=_SRC, capture_output=True, text=True, timeout=5, check=True
            ).stdout.strip()

        commit = git("rev-parse", "--short", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=no", "--", "."))
        return commit + ("+changes" if dirty else "")
    except Exception:
        return "unknown"


def _files(paths: list[Path]) -> list[tuple[Path, Path]]:
    return [
        (root, f)
        for root in paths
        if root.exists()
        for f in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    ]


# File sizes and times -> hash: the contents are read again only after an edit.
_seen: dict[tuple, str] = {}


def _hash(paths: list[Path]) -> str:
    files = _files(paths)
    stamp = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for _, f in files)
    if stamp not in _seen:
        h = hashlib.sha256()
        for root, f in files:
            h.update(f.relative_to(root).as_posix().encode())
            h.update(f.read_bytes())
        _seen[stamp] = h.hexdigest()[:10]
    return _seen[stamp]


def content_hashes() -> dict[str, str]:
    return {name: _hash(paths) for name, paths in CONTENT.items()}


def models(config: Any) -> dict[str, str]:
    from .perceive.understand import perception_model

    speak = config.model
    return {
        "speak": speak,
        "perception": perception_model(speak) or speak,
        "solver": config.solver_model or speak,
        "fallback": os.getenv("LLM_FALLBACK_MODEL") or "-",
        "asr": os.getenv("ASR_BACKEND", "groq") + ":" + os.getenv("GROQ_MODEL", "whisper-large-v3"),
        "tts": os.getenv("TTS_ENGINE", "piper") + ":" + os.getenv("TTS_PIPER_VOICE", "reginute"),
    }


def call_versions(config: Any) -> dict[str, Any]:
    """The tag written on `session_start`."""
    return {"code": code_version(), **content_hashes(), "models": models(config)}
