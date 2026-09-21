"""The analyst — a second pair of ears on the whole call (D-06).

It reads the full transcript, the ledger and the question the engine is waiting on, and
returns typed signals (`signals.py`). It never writes a fact, never changes the
hypothesis and never speaks: `apply` hands each signal to the machinery that already
owns that decision — a contradiction becomes a doubt the caller confirms, an
already-answered fact becomes a confirm question instead of a fresh ask, a secondary
problem joins the closing's list, and tone signals only reach the speaker's card.

Modes (`ANALYST_MODE`): `sync` runs it as the last step of the turn (text, eval),
`async` after the turn in the voice background thread (the signals reach the NEXT turn
through the session inbox), `off` disables it.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .signals import Signal, parse

logger = logging.getLogger(__name__)


def mode(state: Any = None) -> str:
    """`off` disables the analyst; `async` reads it in the voice background thread (the
    reply never waits); `sync` reads it as the last step of the turn (text, eval). An
    explicit ANALYST_MODE wins; otherwise a call with a background window is async and
    everything else sync."""
    env = os.getenv("ANALYST_MODE")
    if env:
        return env.lower()
    return "async" if getattr(getattr(state, "voice", None), "background_reads", False) else "sync"


def read(state: Any, rt: Any) -> list[Signal]:
    """One read of the call. Best-effort: any hiccup returns no signals."""
    if mode(state) == "off":
        return []
    s = state
    if not s.intake.problem_type or s.closing.case_closed or s.closing.is_complete:
        return []
    try:
        from src.services.llm.client import llm_completion

        from ..contract import limits
        from ..perceive.understand import perception_model
        from ..prompts import load_node_prompt

        raw = llm_completion(
            messages=[
                {"role": "system", "content": load_node_prompt("sensors/analyst")},
                {"role": "user", "content": _context(state, rt)},
            ],
            model=perception_model(rt.config.model),
            temperature=0.2,
            # Reasoning models (gpt-oss) burn tokens on hidden thinking BEFORE the
            # answer — a small budget returned an empty string (observed 2026-08-25).
            max_tokens=limits.get("analyst_max_tokens"),
            role="analyst",
        )
        signals = parse(raw, turn_index=s.dialog.turn_count)
    except Exception as e:  # pragma: no cover - the analyst must never break a call
        from ..trace import trace_note

        logger.debug("analyst failed", exc_info=True)
        trace_note(rt.tracer, state, "analyst", str(e), level="error")
        return []
    # Always traced, empty included: "the analyst read this turn and saw nothing" is an
    # observation, and silence in the trace would otherwise be indistinguishable from
    # the analyst never running.
    rt.tracer.emit("analyst_signals", signals=[x.model_dump() for x in signals])
    return signals


def _context(state: Any, rt: Any) -> str:
    """What the analyst reads: the full conversation (it is the ONLY reader of it — the
    speaker's window is short), the deterministic ledger, the belief and the question
    the engine is waiting on."""
    from ..contract import limits
    from ..decide.question import active as active_question
    from ..evidence import summary_lt

    s = state
    history = "\n".join(
        f"{'CALLER' if m['role'] == 'user' else 'AGENT'}: {(m.get('content') or '')[:200]}"
        for m in s.messages[-limits.get("analyst_history_messages") :]
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
    )
    ledger = summary_lt(s.diagnosis.evidence) if s.diagnosis.evidence else "(empty)"
    verdict = (s.resolution.procedure or {}).get("verdict") or "(not set)"
    # Damping (live 2026-09-08): a question asked THIS turn has no answer yet — calling
    # that a drift is noise. The off-topic read only makes sense once the same question
    # needed a re-ask.
    q = active_question(state, rt)
    asked = (
        f"{q.owner}/{q.key} (attempt {q.asks})"
        if q is not None and q.asks >= limits.get("analyst_active_question_min_asks")
        else "(none)"
    )
    return (
        f"CONVERSATION:\n{history}\n\nLEDGER (deterministic facts): {ledger}\n"
        f"HYPOTHESIS: {verdict}\nACTIVE QUESTION: {asked}\n\nSignals (JSON):"
    )


def run_sync(state: Any, rt: Any) -> None:
    """Read and apply in the same turn (text and eval): the signals shape the NEXT
    turn's decisions, exactly as the async ones do."""
    if mode(state) != "sync":
        return
    apply(state, rt, read(state, rt))


def apply(state: Any, rt: Any, signals: list[Signal]) -> None:
    """Hand each signal to the machinery that owns that decision. Stale signals (the
    async read finished after the next turn started) are dropped."""
    fresh = [s for s in signals if s.turn_index >= state.dialog.turn_count - 1]
    tone: list[Signal] = []
    for signal in fresh:
        if signal.type == "contradiction":
            _contradiction(state, rt, signal)
        elif signal.type == "already_answered":
            _already_answered(state, rt, signal)
        elif signal.type == "secondary_problem":
            _secondary_problem(state, rt, signal)
        else:
            tone.append(signal)
    # off_topic / frustration change no decision — they reach the speaker's card only.
    state.voice.analyst_signals = [x.model_dump() for x in tone] or None


def _contradiction(state: Any, rt: Any, signal: Signal) -> None:
    """A ledger fact clashes with what the caller keeps saying: the belief goes into
    doubt and the caller confirms it before anything changes (D-05) — the analyst never
    rewrites the fact itself."""
    from ..decide import hypothesis

    key = signal.fact_key
    if not key:
        return
    entry = state.diagnosis.evidence.get(key) or {}
    if not entry:
        return
    if hypothesis.doubt(
        state, rt, "conflict", key, entry.get("value"), signal.value, source="analyst"
    ):
        rt.tracer.emit("analyst_applied", signal="contradiction", key=key)


def _already_answered(state: Any, rt: Any, signal: Signal) -> None:
    """The caller already answered the fact the engine is about to ask: it becomes a
    confirm question quoting them, never a fresh ask (and never a silent write)."""
    from ..decide import hypothesis

    key, value = signal.fact_key, signal.value
    if not key or not value or key in state.diagnosis.evidence:
        return
    if state.diagnosis.pending_evidence_key and state.diagnosis.pending_evidence_key != key:
        return
    if hypothesis.doubt(state, rt, "flip", key, None, value, source="analyst"):
        rt.tracer.emit("analyst_applied", signal="already_answered", key=key)


def _secondary_problem(state: Any, rt: Any, signal: Signal) -> None:
    """Another complaint mentioned in passing — the closing asks about it once."""
    text = (signal.quote or "").strip()
    if not text or any(x.get("text") == text for x in state.intake.secondary_problems):
        return
    state.intake.secondary_problems.append({"type": None, "text": text, "source": "analyst"})
    rt.tracer.emit("analyst_applied", signal="secondary_problem")
