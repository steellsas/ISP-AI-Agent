"""Speak a TurnPlan's say — a phrase goes out as scripted text; a directive (or a phrase
whose action had no words) is worded by the stage's LLM narrator until M5's speak node."""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer


def speak(state: Any, rt: Any, plan: Any, action_text: str | None) -> str | None:
    from ..contract.locale import phrase

    say = plan.say
    if say.kind == "none":
        return None
    user_input = state.turn.user_input
    if say.kind == "phrase":
        text = phrase(say.key, **say.vars) if say.key else (say.text or action_text)
        if text:
            _speak_text(state, rt, say, user_input, text)
            return text
    return _narrate(state, rt, say.stage, user_input)


def _speak_text(state: Any, rt: Any, say: Any, user_input: str | None, text: str) -> None:
    from ..graph_v2.runtime import speak_scripted

    if say.remember_question:
        speak_scripted(state, rt, _node(say.stage), user_input, text)
        return
    # The opening line: history + trace only — it is not the anchor of the next turn.
    state.turn.active_node = _node(say.stage)
    rt.tracer.emit("node", node=state.turn.active_node, customer_id=state.identity.customer_id)
    state.messages.append({"role": "assistant", "content": text})
    state.turn.reply_path = "greeting" if say.key == "system.greeting" else "scripted"
    rt.tracer.emit("agent_reply", text=text)
    try:
        get_stream_writer()(text)
    except Exception:  # outside a live stream (tests / .invoke) — the text is in state
        pass


def _narrate(state: Any, rt: Any, stage: str | None, user_input: str | None) -> str:
    from ..graph_v2 import runtime as gr
    from ..graph_v2.router import ADDRESS_VALIDATION, CLOSING, TICKET_REGISTRATION

    tools, prompt, node = {
        "closing": (gr.CLOSING_TOOLS, gr.CLOSING_NODE_PROMPT, CLOSING),
        "ticket": (gr.TICKET_TOOLS, gr.TICKET_NODE_PROMPT, TICKET_REGISTRATION),
        "intake": (gr.LOOKUP_TOOLS, gr.ADDRESS_NODE_PROMPT, ADDRESS_VALIDATION),
    }[stage or "intake"]
    return gr.narrate(state, rt, user_input, tools, prompt, node, planned=True)


def _node(stage: str | None) -> str:
    from ..graph_v2.router import ADDRESS_VALIDATION, CLOSING, TICKET_REGISTRATION

    return {"closing": CLOSING, "ticket": TICKET_REGISTRATION}.get(stage or "", ADDRESS_VALIDATION)
