"""
Barge-in — what the caller's words mean when they speak over the agent (PERZIURA §6 I-3).

The Pipecat call (`app/pipecat_call.py`) lets the agent finish its phrase and hold; once the
caller's words are transcribed, `overlap_decision` says "yield" (the caller takes the turn)
or "continue" (the agent goes on from where it stopped):

    a halt word („ne", „stop", „palaukit")  → yield, at any length
    our own words heard back (echo)          → continue
    an answer to the question being asked    → yield
    a bare backchannel („aha", „mhm")        → continue
    anything else                            → yield (default-deny: never swallow a request)
"""

from __future__ import annotations

from .contract import limits
from .contract.locale import vocab


def _fold(text: str) -> str:
    from .evidence import _fold as fold

    return fold(text or "")


def _tokens(text: str) -> list[str]:
    return [t.strip(".,!?…") for t in _fold(text).split() if t.strip(".,!?…")]


def token_overlap(utterance: str, reference: str) -> float:
    """Share of the utterance's tokens present in the reference — FUZZY: a
    token counts when its 4-char prefix appears in the folded reference, so a
    dropped ending ("lempute" vs "lemputės") still matches (agreed
    2026-08-14: Levenshtein/prefix overlap, not a strict `in`)."""
    toks = _tokens(utterance)
    if not toks:
        return 0.0
    ref = _fold(reference)
    hit = sum(
        1 for t in toks if (t[:4] if len(t) >= 4 else t) and (t[:4] if len(t) >= 4 else t) in ref
    )
    return hit / len(toks)


def overlap_decision(
    transcript: str, agent_text: str | None, agent_asked: bool, yes_no: bool = True
) -> str:
    """The caller spoke while the agent was speaking (Pipecat: the agent finished its phrase
    and holds) — "yield" (stop, the caller's words become the turn) or "continue" (go on
    from where it stopped). PERZIURA §6 I-3 (Andrius 2026-10-19/20).

    - nothing readable or ASR noise → continue (nothing was said to us);
    - a halt word („ne", „stop", „palaukit") → yield, at any length;
    - our own words heard back (strict overlap, `barge_echo_overlap`) → continue — strict
      because an answer repeats the question's words („Lemputė nedega su interneto
      simboliu", G1);
    - the agent has asked a question → any words are an answer → yield („Gerai, ačiū." over
      „Ar registruoti?", G17) — except a bare backchannel over an OPEN question („Mhm" over
      „Kuo galiu padėti?" answers nothing, F5);
    - a bare backchannel („aha", „mhm", „taip") → continue;
    - anything else → yield (default-deny: never swallow a real request).
    """
    from adapters.asr.lt_text import is_asr_noise

    toks = _tokens(transcript)
    if not toks or is_asr_noise(transcript):
        return "continue"
    if any(
        t in vocab("barge_stop_tokens") or t.startswith(vocab("barge_stop_prefixes")) for t in toks
    ):
        return "yield"
    if (
        agent_text
        and len(toks) >= 2
        and token_overlap(transcript, agent_text) >= limits.get("barge_echo_overlap")
    ):
        return "continue"
    backchannel = len(toks) <= limits.get("barge_consent_max_words") and all(
        t in vocab("barge_consent_tokens") for t in toks
    )
    if agent_asked:
        return "continue" if backchannel and not yes_no else "yield"
    return "continue" if backchannel else "yield"
