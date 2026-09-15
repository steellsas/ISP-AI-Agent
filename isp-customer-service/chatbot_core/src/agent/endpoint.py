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
detect_farewell) plus the locale's trailing-word list
(vocabulary `continuation_words`). This module is the mechanics. Fail-soft: any
hiccup means "normal".
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from .contract import limits
from .contract.locale import active_language

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=4)
def _trailing_words(language: str) -> frozenset[str]:
    from .contract.locale import vocab
    from .evidence import _fold

    return frozenset(_fold(w) for w in vocab("continuation_words"))


def fast_ms() -> int:
    return limits.get("endpoint_fast_ms")


def slow_ms() -> int:
    return limits.get("endpoint_slow_ms")


def story_ms() -> int:
    return limits.get("endpoint_story_ms")


def classify_endpoint(state: Any, rt: Any, text: str | None) -> tuple[str, int | None]:
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
    if last in _trailing_words(active_language()):
        return ("slow", slow_ms())

    # Complete expected answer: the pending evidence question's deterministic
    # reader maps the whole utterance to a canonical value.
    try:
        pending = state.diagnosis.pending_evidence_key
        r = getattr(state.resolution, "procedure", None) or {}
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
        from .perceive.detectors import detect_farewell

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
        if getattr(state.intake, "problem_type", None) is None:
            return ("slow", story_ms())
    except Exception:  # pragma: no cover
        pass
    return ("normal", None)
