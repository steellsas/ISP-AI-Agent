"""
E2 semantic turn-taking (L4 duplex, sutarta 2026-08-24) — the turn-cut
decision informed by MEANING, not silence alone.

The client's VAD still owns the cut, but the server reads each rolling
partial transcript (E1) and hints how much trailing silence to require:

  - "slow":  the utterance-so-far ends mid-thought (trailing conjunction /
             comma) — wait longer, do not cut the caller off ("nedega, bet…").
  - "fast":  the utterance already IS the complete expected answer (the
             pending evidence question's deterministic reader maps it) or a
             farewell — cut sooner, answer sooner.
  - "normal": anything else — the client's default silence window stands.

Deterministic by design: partials are jittery, so the reading relies only on
the same word-level readers the engine already trusts (read_pending_answer,
detect_farewell) plus a file-editable trailing-word list
(knowledge/endpoint.yaml). Behaviour lives in the file; this module is the
mechanics. Fail-soft: any hiccup means "normal".
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "endpoint.yaml"

# Fallback when the knowledge file is missing/broken — the same piloted list.
_DEFAULT_TRAILING = [
    "bet", "ir", "o", "tai", "nes", "kad", "kai", "arba", "tada", "dar",
    "gal", "nu", "na", "taigi", "vadinasi", "pavyzdžiui",
    "į", "iš", "su", "prie", "ant", "per", "apie",
]  # fmt: skip


@functools.lru_cache(maxsize=1)
def _trailing_words() -> frozenset[str]:
    from .evidence import _fold

    words = _DEFAULT_TRAILING
    try:
        import yaml

        raw = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        loaded = [str(w) for w in (raw.get("tesiniai") or []) if str(w).strip()]
        if loaded:
            words = loaded
    except Exception as e:  # fail-soft: knowledge must never break the call
        logger.warning(f"endpoint vocab load failed ({e}); using built-ins")
    return frozenset(_fold(w) for w in words)


def _ms(env_key: str, default: int) -> int:
    try:
        return int(float(os.environ.get(env_key, str(default))))
    except ValueError:
        return default


def fast_ms() -> int:
    return _ms("ENDPOINT_FAST_MS", 350)


def slow_ms() -> int:
    return _ms("ENDPOINT_SLOW_MS", 1400)


def story_ms() -> int:
    return _ms("ENDPOINT_STORY_MS", 1800)


def classify_endpoint(engine: Any, text: str | None) -> tuple[str, int | None]:
    """(mode, silence_ms) for the utterance-so-far; ("normal", None) on any
    doubt. Order matters: an unfinished thought outranks a mapped answer —
    "nedega, bet" must WAIT even though "nedega" maps."""
    stripped = (text or "").strip()
    if not stripped:
        return ("normal", None)
    from .evidence import _fold

    # Unfinished thought: trailing comma/dash or a trailing connective word.
    bare = stripped.rstrip(".!?")
    if bare.endswith((",", "-", "—", "…")):
        return ("slow", slow_ms())
    last = _fold(bare).split()[-1] if _fold(bare).split() else ""
    if last in _trailing_words():
        return ("slow", slow_ms())

    # Complete expected answer: the pending evidence question's deterministic
    # reader maps the whole utterance to a canonical value.
    try:
        pending = getattr(engine, "_evidence_last_ask_key", None)
        r = getattr(engine.state, "resolution", None) or {}
        if pending and r.get("verdict"):
            from .evidence import read_pending_answer, spec_for

            spec = spec_for(r.get("verdict")) or {}
            item = (spec.get("client") or {}).get(pending)
            if read_pending_answer(str(pending), stripped, item) is not None:
                return ("fast", fast_ms())
    except Exception:  # pragma: no cover - a hint must never break a partial
        logger.debug("endpoint fast-check failed", exc_info=True)

    # A farewell is complete by definition — close the turn promptly.
    try:
        from .resolution import detect_farewell

        if detect_farewell(stripped):
            return ("fast", fast_ms())
    except Exception:  # pragma: no cover
        pass
    # STORY window (2026-09-02, live: „Ora šiandien kažkoks netoks. [pauzė]
    # gal dėl to neturiu interneto?" was cut at the pause and the agent
    # answered half a thought): while the call's PROBLEM is not yet known the
    # caller is TELLING a story — pauses between thoughts are natural, so the
    # cut waits longer. Once the problem is set, answers return to the normal
    # window.
    try:
        if getattr(engine.state, "problem_type", None) is None:
            return ("slow", story_ms())
    except Exception:  # pragma: no cover
        pass
    return ("normal", None)
