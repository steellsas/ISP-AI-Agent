"""What the speaking LLM sees: the cached prompt prefix, the history window and the
context card.

Prompt-cache friendliness: the system prefix (core prompt + the owner's snippet) is
byte-stable per owner, so providers keep it warm; the card changes every turn and
therefore rides in a SEPARATE trailing system message instead of being concatenated
into the prefix (concatenating would bust the cache every turn — the real cost).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

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
