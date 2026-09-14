"""
Voice transport reports between turns — what the caller actually heard and said
while the agent was speaking. The session applies them to the checkpointed
state outside a turn (AgentSession._write_between_turns).

- apply_overlay: the caller's words spoken OVER the agent's voice.
- apply_delivery: how many sentences of the reply finished playing (D1 ledger).
"""

from __future__ import annotations

from typing import Any


def apply_overlay(state: Any, rt: Any, texts: list[str]) -> None:
    """Duplex-hearing 2: the caller's words spoken OVER the agent's voice
    (echo already filtered by the transport) — deterministic fact ingest
    through the importance gates + a one-shot narrator note. Overlay may
    FILL facts, never steer routing."""
    from .perception_flow import ingest_overlay

    kept = [t.strip() for t in texts if t and t.strip()][:3]
    if not kept:
        return
    for text in kept:
        ingest_overlay(state, rt, text)
    state.voice.overlay_heard = kept
    rt.tracer.emit("overlay_applied", texts=[t[:120] for t in kept])


def apply_delivery(state: Any, rt: Any, sentences: list[str], delivered: int) -> None:
    """D1 delivery ledger (live 2026-08-25: the transcript renders before
    the audio, so a barge-in leaves the engine believing the caller heard
    the WHOLE reply). The transport reports how many sentences actually
    finished playing — the history keeps only that prefix, and the unheard
    tail is surfaced to the narrator next turn. A half-played sentence
    counts as NOT heard (repeating it is the natural repair)."""
    total = len(sentences)
    delivered = max(0, min(int(delivered), total))
    if not total or delivered >= total:
        return
    heard = " ".join(s.strip() for s in sentences[:delivered]).strip()
    tail = " ".join(s.strip() for s in sentences[delivered:]).strip()
    s = state
    for msg in reversed(s.messages):
        if msg.get("role") == "assistant":
            msg["content"] = (heard + " —") if heard else "—"
            break
    state.voice.undelivered_tail = tail or None
    # Andrius 2026-08-26: the agent must NEVER believe it asked a question
    # the caller could not hear. When the "?" lives only in the unheard
    # tail, the ask never happened: the pending evidence key and its ask
    # counter roll back (the caller's next words are NOT an answer to it),
    # the step's presented counter steps back, and the narrator gets a
    # STRONG re-ask directive instead of the advisory tail note.
    # Closing-stage chatter is exempt (live 2026-08-27): garbled farewells
    # kept cutting the goodbye before its "?" and the re-ask machinery
    # looped "Ar dar kuo padėti?" — a closed case never re-asks.
    if "?" in tail and "?" not in heard and not s.closing.case_closed:
        s.dialog.last_question = None
        # The PENDING evidence key deliberately STAYS (live 2026-08-27:
        # clearing it looped the call — the caller kept interrupting with
        # the ANSWER, which then had no key to land on, so the fact never
        # committed and the same question re-asked forever). Only the ask
        # counter steps back so the wording escalation stays fair; an
        # answer that maps still commits, a true non-answer re-asks anyway.
        key = state.diagnosis.pending_evidence_key
        if key and state.diagnosis.evidence_ask_counts.get(key, 0) > 0:
            state.diagnosis.evidence_ask_counts[key] -= 1
        r = s.resolution.procedure or {}
        pres = r.get("presented") or {}
        step_id = r.get("step")
        if step_id and pres.get(step_id, 0) > 0:
            pres[step_id] -= 1
        state.voice.unheard_question = tail
        state.voice.undelivered_tail = None  # superseded by the strong directive
    rt.tracer.emit(
        "delivery",
        delivered=delivered,
        total=total,
        unheard=tail[:160],
        question_unheard=bool(state.voice.unheard_question),
    )
