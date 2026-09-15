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
    if say.reply_layer:
        return _narrate_stage(state, rt, plan, user_input)
    return _narrate(state, rt, say.stage, user_input, planned=True)


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


def _narrate_stage(state: Any, rt: Any, plan: Any, user_input: str | None) -> str:
    """A stage directive: the narrator's scripted exits may still take the turn (and
    record their own plan); otherwise the LLM words the stage."""
    from ..decide.plan import record, record_stage_reply
    from ..narrator_flow import mark_step_presented

    stage = plan.say.stage
    state.turn.plan = None
    reply = _narrate(state, rt, stage, user_input, planned=False)
    if stage in ("intake", "diagnosis"):
        mark_step_presented(state, rt)
        record_stage_reply(
            state, "identification.free_reply" if stage == "intake" else "diagnosis.free_reply"
        )
    elif state.turn.plan is None:
        record(state, plan)
    return reply


def _narrate(state: Any, rt: Any, stage: str | None, user_input: str | None, planned: bool) -> str:
    from ..graph_v2 import runtime as gr

    tools, prompt = {
        "closing": (gr.CLOSING_TOOLS, gr.CLOSING_NODE_PROMPT),
        "ticket": (gr.TICKET_TOOLS, gr.TICKET_NODE_PROMPT),
        "intake": (gr.LOOKUP_TOOLS, gr.ADDRESS_NODE_PROMPT),
        "diagnosis": (None, gr.DIAGNOSIS_NODE_PROMPT),
        "side_topic": (frozenset(), gr.SIDE_TOPIC_PROMPT),
    }[stage or "intake"]
    return gr.narrate(
        state, rt, user_input, tools, prompt, NODES[stage or "intake"], planned=planned
    )


def _stream(text: str) -> None:
    try:
        get_stream_writer()(text)
    except Exception:  # outside a live stream (tests / .invoke) — the text is in state
        pass
