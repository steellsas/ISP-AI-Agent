"""Speak a TurnPlan's say — a phrase goes out as scripted text; a directive (or a phrase
whose action had no words) is worded by the stage's LLM narrator until M5's speak node."""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

# Stage -> the node name the narrator traces (kept for trace/test parity).
NODES = {
    "intake": "address_validation",
    "diagnosis": "diagnosis",
    "side_topic": "side_topic",
    "ticket": "ticket_registration",
    "closing": "closing",
}


def speak(state: Any, rt: Any, plan: Any, action_text: str | None) -> str | None:
    from ..contract.locale import phrase

    say = plan.say
    if say.kind == "none":
        return None
    user_input = state.turn.user_input
    if say.kind == "phrase":
        text = phrase(say.key, **say.vars) if say.key else (say.text or action_text)
        if text and say.committed:
            _stream(text)  # the engine already put the words on the history and trace
            return text
        if text:
            _speak_text(state, rt, say, user_input, text)
            return text
    reply = _narrate(state, rt, say.stage, user_input)
    if say.stage in ("intake", "diagnosis"):
        from .step import mark_step_presented

        mark_step_presented(state, rt)
    return reply


def _speak_text(state: Any, rt: Any, say: Any, user_input: str | None, text: str) -> None:
    from ..graph_v2.runtime import speak_scripted

    node = NODES[say.stage or "intake"]
    if say.remember_question:
        speak_scripted(state, rt, node, user_input, text)
        return
    # The opening line: history + trace only — it is not the anchor of the next turn.
    state.turn.active_node = node
    rt.tracer.emit("node", node=node, customer_id=state.identity.customer_id)
    state.messages.append({"role": "assistant", "content": text})
    rt.tracer.emit("agent_reply", text=text)
    _stream(text)


def _narrate(state: Any, rt: Any, stage: str | None, user_input: str | None) -> str:
    from ..graph_v2 import runtime as gr

    owner = stage or "intake"
    return gr.narrate(state, rt, user_input, owner, NODES[owner])


def _stream(text: str) -> None:
    try:
        get_stream_writer()(text)
    except Exception:  # outside a live stream (tests / .invoke) — the text is in state
        pass


def emit_scripted(state: Any, rt: Any, text: str) -> str:
    """Bookkeeping for an engine-composed reply: history, the anchor question, trace."""
    from ..dialog_utils import is_question
    from ..trace import emit_case

    state.messages.append({"role": "assistant", "content": text})
    if is_question(text):
        state.dialog.last_question = text
    emit_case(rt.tracer, state)
    rt.tracer.emit("scripted", where="identification")
    rt.tracer.emit("agent_reply", text=text)
    return text


def commit_driven(state: Any, rt: Any, user_input: str | None, reply: str) -> str:
    """End-of-turn bookkeeping for a solver-led reply (the speaker's path does the same
    in begin_turn): the user_turn trace, the dialogue history, the shared finalisation."""
    from ..speak.postprocess import finalize, trim_to_cap

    reply = trim_to_cap(state, rt, reply)
    # The caller's words are already on the history (the perceive node put them there).
    state.messages.append({"role": "assistant", "content": reply})
    finalize(state, rt, reply)
    return reply
