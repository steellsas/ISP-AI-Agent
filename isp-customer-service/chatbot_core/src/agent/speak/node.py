"""What the speaking LLM sees: the cached prompt prefix, the history window and the
context card.

Prompt-cache friendliness: the system prefix (core prompt + the owner's snippet) is
byte-stable per owner, so providers keep it warm; the card changes every turn and
therefore rides in a SEPARATE trailing system message instead of being concatenated
into the prefix (concatenating would bust the cache every turn — the real cost).
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from functools import lru_cache
from typing import Any

from src.services.llm.client import get_last_call_stats, stream_tool_completion

from ..trace import trace_note

logger = logging.getLogger(__name__)

# Plan owners that have their own snippet; every other owner speaks with the core
# prompt alone.
OWNERS = ("intake", "diagnosis", "ticket", "closing", "side_topic")


@lru_cache(maxsize=32)
def speak_prompt(owner: str, caller_phone: str, language: str) -> str:
    """The byte-stable prefix for this owner (core prompt + the owner's snippet)."""
    from ..prompts import load_node_prompt, load_speak_prompt

    parts = [load_speak_prompt(caller_phone=caller_phone, language=language)]
    if owner in OWNERS:
        parts.append(load_node_prompt(f"speak/owners/{owner}"))
    return "\n\n".join(parts)


def build_messages(state: Any, rt: Any, owner: str) -> list[dict]:
    """The payload for one speaking call: prefix, history summary, window, card."""
    from .context_card import context_card
    from .history import history_summary, prune_history

    messages = [
        {
            "role": "system",
            "content": speak_prompt(owner, state.identity.caller_phone, rt.config.language),
        }
    ]
    # When the window cut older turns, a short DETERMINISTIC summary from STATE bridges
    # the gap — the speaker never sees a conversation that starts mid-air.
    summary = history_summary(state, rt)
    if summary:
        messages.append({"role": "system", "content": summary})
    messages.extend(prune_history(state, rt, state.messages))
    card = context_card(state, rt)
    if card:
        messages.append({"role": "system", "content": card})
    _debug(state, rt, card, messages)
    return messages


def _debug(state: Any, rt: Any, card: str | None, messages: list[dict]) -> None:
    """What the LLM actually SEES this turn — where "why did it say that" lives. Off by
    default (it would bloat the trace); DEBUG_LLM=1 turns it on, =full adds the
    messages."""
    if not os.environ.get("DEBUG_LLM"):
        return
    payload: dict[str, Any] = {
        "node": state.turn.active_node,
        "card": card,
        "history_msgs": len(messages) - 1,
    }
    if os.environ.get("DEBUG_LLM") == "full":
        payload["messages"] = messages
    rt.tracer.emit("llm_input", **payload)


def turn(state: Any, rt: Any, user_input: str | None, owner: str):
    """One speaking turn: a generator that YIELDS the reply's text tokens as the LLM
    produces them. Every decision — including the scripted exits — happened before."""
    begin_turn(state, rt, user_input)
    yield from stream_reply(state, rt, owner)


def begin_turn(state: Any, rt: Any, user_input: str | None) -> None:
    """The turn's bookkeeping before any words: the barge-in flag, the heard text and
    intent, the background telemetry fold, the history."""
    from ..background import apply_bg_diagnosis
    from ..perceive.detectors import detect_turn_intent

    rt.cancel.clear()  # a stale barge-in never cancels a NEW turn
    # Ticket-dialogue turns skip the diagnosis ingest — without this, the PREVIOUS
    # turn's "understood" directive leaks into their replies.
    if state.ticket.stage:
        state.turn.understanding = None
    state.dialog.last_heard = (user_input or "").strip()
    state.dialog.last_intent = detect_turn_intent(user_input)
    # S2 (2026-08-24): a background telemetry read finished while the caller was busy —
    # fold it in at the deterministic turn start, but ONLY as a refresh: in the
    # solution/bridge phase, or when the fresh verdict FLIPS the story, it is discarded
    # (live: the bg read saw the just-plugged PC, the narrative turned foreign_mac
    # mid-bridge and the agent asked "ar keitėte routerį?" over a working bind).
    apply_bg_diagnosis(state, rt)
    # The caller's utterance goes on the history for EVERY reply path (review
    # 2026-08-07): scripted turns used to skip it, so the LLM later saw a conversation
    # with holes and re-asked answered questions.
    if user_input:
        rt.tracer.emit("user_turn", text=user_input)
        state.messages.append({"role": "user", "content": user_input})


def stream_reply(state: Any, rt: Any, owner: str):
    """Stream the speaker's reply token by token. No tools: the engine already ran every
    check and action, and the plan says what this reply must achieve."""
    from .postprocess import finish

    for _attempt in range(rt.config.max_tool_calls_per_response):
        state.dialog.turn_count += 1
        if state.dialog.turn_count > state.dialog.max_turns:
            yield rt.config.max_turns_message
            return

        # The user message is already on the history (appended up front, so scripted
        # turns record it too); the prompt builds from history.
        messages = build_messages(state, rt, owner)
        try:
            content = yield from _stream_tokens(state, rt, messages)
        except _Cancelled:
            return
        except Exception as e:  # pragma: no cover - provider/transport failures
            logger.error(f"LLM stream error: {e}")
            trace_note(rt.tracer, state, "llm_stream", str(e), level="error")
            yield rt.config.error_message
            return
        record_llm_stats(state, rt)

        if not content:
            # Empty reply (already yielded nothing) -> nudge and retry.
            state.messages.append({"role": "assistant", "content": ""})
            state.messages.append(
                {
                    "role": "user",
                    "content": "Your last reply was empty. Write a message to the customer.",
                }
            )
            continue

        # The reply text was already streamed; the guards may still append to it (a
        # registration claim with no ticket behind it), and only that extra needs
        # streaming.
        _reply, extra = finish(state, rt, content)
        if extra:
            yield extra
        return

    yield rt.config.timeout_message


class _Cancelled(Exception):
    """A barge-in closed the stream mid-generation."""


def _stream_tokens(state: Any, rt: Any, messages: list[dict]):
    """Yield the reply's tokens and return the final text. Manual consumption instead of
    `yield from`: the cancel flag is checked BETWEEN TOKENS — closing the inner
    generator closes the LLM HTTP stream, so the generation itself stops (PR3)."""
    inner = stream_tool_completion(
        messages=messages,
        tools=None,
        model=rt.config.model,
        temperature=rt.config.temperature,
        max_tokens=rt.config.max_tokens,
    )
    streamed: list[str] = []
    while True:
        try:
            token = next(inner)
        except StopIteration as done:
            return (getattr(done.value, "content", None) or "").strip()
        if rt.cancel.is_set():
            with suppress(Exception):
                inner.close()
            on_turn_cancelled(state, rt, "".join(streamed))
            raise _Cancelled
        if isinstance(token, str):
            streamed.append(token)
        yield token


def on_turn_cancelled(state: Any, rt: Any, spoken_text: str) -> None:
    """Barge-in cut the reply mid-generation (Phase 5 PR3): record what the caller
    ACTUALLY heard. The ask-bookkeeping is deliberately NOT rolled back (review
    2026-08-07): the NEXT turn decides — an early answer ("taip, dega raudona!") routes
    normally, a question goes through side_topic with the anchor, and an unclear reply
    holds -> the question re-asks naturally. A blanket re-ask made the agent feel robotic
    when callers interrupted BECAUSE they had already understood."""
    spoken = (spoken_text or "").strip()
    state.messages.append({"role": "assistant", "content": (spoken + " —") if spoken else "—"})
    # An evidence ask that never fully went out must not escalate the wording.
    key = state.diagnosis.pending_evidence_key
    if key and state.diagnosis.evidence_ask_counts.get(key, 0) > 0:
        state.diagnosis.evidence_ask_counts[key] -= 1
    rt.tracer.emit("turn_cancelled", spoken=spoken[:160])


def record_llm_stats(state: Any, rt: Any) -> None:
    """Fold the last LLM call's stats into the running totals + trace."""
    s = get_last_call_stats()
    rt.llm_stats.add_call(
        input_tokens=s.get("input_tokens", 0),
        output_tokens=s.get("output_tokens", 0),
        cost=s.get("cost", 0),
        latency_ms=s.get("latency_ms", 0),
        cached=s.get("cached", False),
        model=s.get("model", rt.config.model),
    )
    rt.tracer.emit(
        "llm",
        model=s.get("model", rt.config.model),
        input_tokens=s.get("input_tokens", 0),
        output_tokens=s.get("output_tokens", 0),
        latency_ms=round(s.get("latency_ms", 0)),
        cached=s.get("cached", False),
    )
