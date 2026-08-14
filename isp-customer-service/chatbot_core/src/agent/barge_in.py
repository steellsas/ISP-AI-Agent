"""
Smart barge-in (VOICE_PLAN L3a) — what an interruption MEANS.

The transport kills playback on any speech; this module decides what to do
with the interrupting utterance once transcribed:

    "stop"        — a negation/halt word: a REAL interruption, process it.
    "consent"     — a bare backchannel ("taip", "gerai", "mhm"): the caller is
                    agreeing along, not taking the turn — do not derail.
    "echo"        — the transcript is the AGENT'S OWN words leaking back from a
                    speakerphone (fuzzy token overlap with what was just being
                    said — Whisper garbles 1–2 endings, so no exact match).
    "substantive" — anything else: real content, process it as a normal turn.

DEFAULT-DENY (sutarta 2026-08-14): anything unclear is "substantive" — the
worst case is today's behaviour, never a swallowed real request. Negation
beats consent at any length ("ne!" stops the agent, always).
"""

from __future__ import annotations

# Positive backchannel tokens — the ONLY words treated as agreeing-along.
CONSENT_TOKENS = (
    "taip",
    "gerai",
    "aha",
    "mhm",
    "mhmm",
    "aišku",
    "aisku",
    "klausau",
    "supratau",
    "ok",
    "okey",
    "jo",
    "nu",
    "puiku",
)

# Halt/negation tokens — hard stop regardless of the utterance length.
STOP_TOKENS = (
    "ne",
    "ne.",
    "stop",
    "stok",
    "palauk",
    "palaukit",
    "palaukite",
    "blogai",
    "nereikia",
    "netaip",
    "nesupratau",
)

_ECHO_OVERLAP = 0.8  # fuzzy token overlap (>=) that reads as our own echo
_MAX_CONSENT_WORDS = 3  # longer than this is content, not a backchannel


def _fold(text: str) -> str:
    from .evidence import _fold as fold

    return fold(text or "")


def _tokens(text: str) -> list[str]:
    return [t.strip(".,!?…") for t in _fold(text).split() if t.strip(".,!?…")]


def token_overlap(utterance: str, reference: str) -> float:
    """Share of the utterance's tokens present in the reference — FUZZY: a
    token counts when its 4-char prefix appears in the folded reference, so a
    dropped ending ("lempute" vs "lemputės") still matches (sutarta
    2026-08-14: Levenshtein/prefix overlap, ne griežtas `in`)."""
    toks = _tokens(utterance)
    if not toks:
        return 0.0
    ref = _fold(reference)
    hit = sum(
        1 for t in toks if (t[:4] if len(t) >= 4 else t) and (t[:4] if len(t) >= 4 else t) in ref
    )
    return hit / len(toks)


def classify_interruption(transcript: str, agent_text: str | None) -> str:
    """See the module docstring. `agent_text` is what the agent was SAYING when
    interrupted (its own last spoken words) — the echo reference."""
    toks = _tokens(transcript)
    if not toks:
        return "substantive"  # unreadable — default-deny
    # Negation wins at any length — an urgent halt must never be swallowed.
    if any(t in STOP_TOKENS or t.startswith(("nesta", "nebe")) for t in toks):
        return "stop"
    if agent_text and len(toks) >= 2 and token_overlap(transcript, agent_text) >= _ECHO_OVERLAP:
        return "echo"
    if len(toks) <= _MAX_CONSENT_WORDS and all(t in CONSENT_TOKENS for t in toks):
        return "consent"
    return "substantive"
