"""
Dialogue helpers — small pure reads over the call state and reply text
(repeat-guard comparison, the last question asked, message shapes).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .contract.locale import phrase, vocab_set


def last_agent_question(state: Any) -> str | None:
    """The last thing the agent actually said — the real question the caller is
    answering (a better classifier context than the English step hint)."""
    for m in reversed(state.messages):
        if m.get("role") == "assistant" and (m.get("content") or "").strip():
            return m["content"]
    return None


def asked_recently(state: Any, r: dict) -> bool:
    """True when the current step's question actually went out within the
    last ~3 exchanges. Steps presented long ago (walker benched by the
    solver/evidence drive) may not read new replies as their answers —
    test/legacy setups without the stamp count as fresh."""
    at = r.get("asked_at")
    if at is None:
        return True
    return len(state.messages) - at <= 6


def is_question(text: str) -> bool:
    return text.strip().endswith("?")


def sanitize_question(text: str) -> str:
    """Lowercase, drop punctuation + politeness fillers, collapse whitespace —
    so two questions compare on their CORE, not their wording trim."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
    return " ".join(w for w in cleaned.split() if w not in vocab_set("stuck_filler"))


def similar(a: str, b: str) -> bool:
    """True if two questions are effectively the same re-ask (containment, to
    catch an added prefix, or a high difflib ratio on the sanitized cores)."""
    sa, sb = sanitize_question(a), sanitize_question(b)
    if not sa or not sb:
        return False
    if sa in sb or sb in sa:
        return True
    return SequenceMatcher(None, sa, sb).ratio() > 0.8


def progress_key(state: Any) -> list:
    """A snapshot of the fields that mean the conversation ADVANCED. Compared
    start-vs-end of a turn: if it changed, the turn made real progress (a slot
    filled, identified, an outage found, the case closed) — so the stuck
    counter resets. Text changing alone is NOT progress (docs: reset on state,
    not on a reworded question)."""
    p = state.identity.profile
    filled = sum(
        1 for slot in (p.city, p.street, p.house, p.apartment, p.account_code) if slot.value
    )
    return [
        state.identity.customer_id,
        filled,
        state.intake.problem_type,
        state.diagnosis.outage_reported,
        state.closing.case_closed,
        state.ticket.ticket_id,
    ]


def anchor_text(state, rt) -> str:
    """The exact place to return to after a deviation — the engine's LAST
    asked question (deterministic), never the LLM's memory of it. Trimmed
    to the QUESTION sentence only: anchoring the whole reply re-read a long
    announce back at the caller (live 2026-08-10)."""
    q = (state.dialog.last_question or "").strip()
    if not q:
        return phrase("system.default_anchor")
    sentences = re.split(r"(?<=[.!?])\s+", q)
    questions = [x for x in sentences if x.strip().endswith("?")]
    return (questions[-1] if questions else sentences[-1]).strip()
