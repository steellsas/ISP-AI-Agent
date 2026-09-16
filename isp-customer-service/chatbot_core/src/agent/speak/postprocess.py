"""Safety passes over a spoken reply — never decisions, only what may leave the mouth.

Three of them, in order: a registration claim that has no ticket behind it starts the
contact dialogue on the same breath, a reply longer than the phone-call cap is trimmed
at a sentence boundary, and the repeat guard records whether this reply re-asked the
last question (the stuck ladder the rules read next turn).
"""

from __future__ import annotations

import re
from typing import Any

# A sentence ends at . ! ? … — the cap never cuts mid-sentence.
_SENTENCE_END = re.compile(r"[.!?…]['\"“”„»)]*\s")


def finish(state: Any, rt: Any, text: str) -> tuple[str, str]:
    """The full reply and the EXTRA words the guards appended (the caller has already
    heard everything before them, so only the extra still needs streaming)."""
    from ..execute.ticket import registration_claim_guard

    text = trim_to_cap(state, rt, text)
    extra = registration_claim_guard(state, rt, text) or ""
    reply = text + extra
    state.messages.append({"role": "assistant", "content": reply})
    finalize(state, rt, reply)
    return reply, extra


def trim_to_cap(state: Any, rt: Any, text: str) -> str:
    """A phone caller cannot hold a paragraph: past the cap the reply is cut at the last
    sentence that fits (never mid-sentence — a dangling half-sentence is worse than a
    long one, so a single long sentence goes out whole)."""
    from ..contract import limits

    cap = limits.get("reply_max_chars")
    if len(text) <= cap:
        return text
    ends = [m.end() for m in _SENTENCE_END.finditer(text) if m.end() <= cap]
    if not ends:
        return text
    trimmed = text[: ends[-1]].strip()
    rt.tracer.emit("reply_trimmed", was=len(text), now=len(trimmed))
    return trimmed


def finalize(state: Any, rt: Any, text: str) -> None:
    """Shared end-of-turn bookkeeping for a customer-facing reply: the repeat guard, the
    goodbye check, the case snapshot and the reply trace."""
    from ..execute.say import maybe_end_on_goodbye
    from ..trace import emit_case

    track_stuck(state, rt, text)
    maybe_end_on_goodbye(state, rt, text)
    emit_case(rt.tracer, state)
    rt.tracer.emit("agent_reply", text=text)


def track_stuck(state: Any, rt: Any, reply: str) -> None:
    """Update the stuck counter from this turn's outcome. Increment ONLY when the agent
    actually RE-ASKS the same question (a genuine loop) — a new/different question or
    normal back-and-forth must not escalate. Real progress (a slot, customer_id or
    problem change since the turn started) clears it. Records last_question for the next
    turn's repeat check."""
    from ..dialog_utils import is_question, progress_key, similar

    progressed = progress_key(state) != state.turn.progress_key_at_start
    is_q = is_question(reply)
    repeat = bool(
        is_q and state.dialog.last_question and similar(reply, state.dialog.last_question)
    )
    state.dialog.last_reply_repeated = repeat
    if progressed:
        state.dialog.stuck_count = 0
    elif repeat:
        state.dialog.stuck_count += 1
    # else: a different question or a statement leaves the counter unchanged — only a
    # real re-ask escalates, and only real progress clears it.
    if is_q:
        state.dialog.last_question = reply
    rt.tracer.emit("stuck", count=state.dialog.stuck_count, repeated=repeat)
