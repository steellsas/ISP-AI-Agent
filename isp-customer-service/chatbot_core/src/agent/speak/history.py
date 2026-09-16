"""The message window — what of the conversation the speaker sees.

The whole history is never resent: a recent window plus a deterministic summary of what
the window cut, so the speaker never sees a conversation that starts mid-air. When the
caller references their OWN earlier words, the matching old lines are pulled back in."""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from ..contract.locale import phrase_or


def history_summary(state, rt) -> str | None:
    """Hygiene step 3 (istorija v2, Andrius 2026-08-27): when older turns fall
    out of the window, the narrator gets a 1–2 line DETERMINISTIC summary
    built from STATE — zero LLM cost, never hallucinates, always fresh. The
    full transcript stays in GraphState.messages (nothing is deleted)."""
    s = state
    if len(s.messages) <= rt.config.history_window_messages:
        return None  # nothing was cut — no summary needed
    bits: list[str] = []
    if s.intake.problem_type:
        when_code, trig_code = s.intake.anamnesis_when, s.intake.anamnesis_trigger
        when = f", dingo {phrase_or(f'anamnesis.when.{when_code}', when_code)}" if when_code else ""
        trig = (
            f", po: {phrase_or(f'anamnesis.trigger.{trig_code}', trig_code)}" if trig_code else ""
        )
        bits.append(f"Problema: {s.intake.problem_type}{when}{trig}")
    if s.identity.customer_id:
        bits.append(f"Klientas: {s.identity.customer_address or s.identity.customer_id}")
    if s.identity.caller_name:
        bits.append(f"skambina {s.identity.caller_name}")
    r = s.resolution.procedure or {}
    if r.get("verdict"):
        gloss = phrase_or(f"verdict.{r['verdict']}.gloss", r["verdict"])
        bits.append(f"Diagnozė: {gloss}")
    if s.diagnosis.evidence:
        from ..evidence import summary_lt

        est = summary_lt(s.diagnosis.evidence)
        if est:
            bits.append(f"Nustatyta: {est}")
    if s.ticket.ticket_id:
        bits.append(f"Tiketas: {s.ticket.ticket_id}")
    if not bits:
        return None
    return (
        "POKALBIO PRADŽIOS SANTRAUKA (senesnės replikos praleistos; faktai "
        "galioja): " + "; ".join(bits) + "."
    )


_RECALL_MARKS = ("minejau", "sakiau", "kartoju", "jau aiskinau", "anksciau sakiau")


def recall_lines(state, rt) -> str | None:
    """Hygiene step 3 — the RECALL trigger: when the caller references their
    own earlier words ("juk SAKIAU…"), the matching OLD user lines (outside
    the window) are pulled back into the facts block for THIS turn. Pure
    keyword overlap on folded content words — no vectors, no latency."""
    from ..evidence import _fold

    s = state
    heard = _fold(s.dialog.last_heard or "")
    if not heard or not any(m in heard for m in _RECALL_MARKS):
        return None
    window = rt.config.history_window_messages
    old = s.messages[:-window] if len(s.messages) > window else []
    old_user = [m.get("content") or "" for m in old if m.get("role") == "user"]
    if not old_user:
        return None
    words = {w for w in heard.split() if len(w) >= 5}
    scored = []
    for text in old_user:
        overlap = sum(1 for w in _fold(text).split() if len(w) >= 5 and w in words)
        if overlap:
            scored.append((overlap, text))
    if not scored:
        return None
    scored.sort(key=lambda p: -p[0])
    picks = [t[:160] for _n, t in scored[:2]]
    quoted = " / ".join(f"„{t}“" for t in picks)
    return (
        "- KLIENTAS PRIMENA, KĄ SAKĖ ANKSČIAU — jo ankstesnės frazės: "
        f"{quoted}. Atsižvelk į jas ir neprašyk kartoti."
    )


def prune_history(state, rt, messages: list) -> list:
    """
    Return the most recent slice of history that fits the configured window.

    Pairing safety: native tool calling requires every role:"tool" message to
    be preceded by the assistant message that issued the matching tool_calls.
    A naive "last N" cut can land mid-exchange and orphan a tool result, which
    the chat API rejects (400). So if the window would start on a tool result,
    we walk the start index left until it lands on the owning assistant
    message, keeping the exchange intact.
    """
    window = rt.config.history_window_messages
    if window <= 0 or len(messages) <= window:
        return list(messages)

    start = len(messages) - window
    while start > 0 and messages[start].get("role") == "tool":
        start -= 1
    return messages[start:]
