"""Speak a TurnPlan's say — a phrase goes out as scripted text; a directive (or a phrase
whose action had no words) is worded by the stage's LLM narrator until M5's speak node."""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from ..contract.locale import vocab

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
        "intake": (frozenset(), gr.ADDRESS_NODE_PROMPT),
        "diagnosis": (None, gr.DIAGNOSIS_NODE_PROMPT),
        "side_topic": (frozenset(), gr.SIDE_TOPIC_PROMPT),
    }[stage or "intake"]
    return gr.narrate(
        state, rt, user_input, tools, prompt, NODES[stage or "intake"], exits=not planned
    )


def _stream(text: str) -> None:
    try:
        get_stream_writer()(text)
    except Exception:  # outside a live stream (tests / .invoke) — the text is in state
        pass


# --- The narrator's scripted exits (§5 rows 11-15 and 18-19) -----------------------------


def scripted_exit(state: Any, rt: Any) -> str | None:
    """The engine's words for a stage turn, after the narrator's turn bookkeeping: the
    stuck backstop, the scripted reply layer, the wait acknowledgement. Each records its
    plan; None = the LLM words the stage."""
    from ..decide.rules.dialog import scripted_wait_ack, stuck_backstop
    from ..decide.rules.reply import plan_reply
    from .actions import run_action

    backstop = stuck_backstop(state)
    if backstop is not None:
        _record(state, "dialog.stuck_backstop")
        return apply_backstop(state, rt, backstop)
    plan = plan_reply(state, rt, state.dialog.last_heard)
    if plan is not None:
        from ..decide.plan import record

        record(state, plan)
        if plan.say.kind == "phrase":
            action_text = run_action(state, rt, plan)
            words = plan.say.text or action_text
            if words:
                return emit_scripted(state, rt, words)
    wait = scripted_wait_ack(state, rt)
    if wait is not None:
        _record(state, "dialog.wait_ack")
        return emit_scripted(state, rt, wait)
    return None


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


def apply_backstop(state: Any, rt: Any, backstop: tuple[str, bool]) -> str:
    """Speak the stuck backstop (it climbs 3 -> 4 -> close); F-5: its close keeps the
    registration promise for an identified caller and records an unidentified one."""
    from ..dialog_utils import is_question
    from ..trace import emit_case
    from .say import maybe_end_on_goodbye

    text, should_close = backstop
    if should_close:
        _close_stuck(state, rt)
    else:
        state.dialog.stuck_count += 1  # advance the ladder for the next turn
    state.messages.append({"role": "assistant", "content": text})
    if is_question(text):
        state.dialog.last_question = text
    maybe_end_on_goodbye(state, rt, text)
    emit_case(rt.tracer, state)
    rt.tracer.emit("stuck", count=state.dialog.stuck_count, repeated=False)
    rt.tracer.emit("agent_reply", text=text)
    return text


def _close_stuck(state: Any, rt: Any) -> None:
    from ..decide.plan import Action
    from ..executor_flow import register_ticket_from_state

    s = state
    s.closing.case_closed = True
    if s.identity.customer_id:
        if s.resolution.procedure is not None:
            s.resolution.procedure["escalate_reason"] = "stuck"
        register_ticket_from_state(s, rt, None)
        s.closing.closed_reason = "registered" if s.ticket.ticket_id else "declined"
        _record(state, "dialog.stuck_backstop", Action(type="register_ticket", name="stuck"))
        return
    s.closing.closed_reason = "declined"
    s.closing.unidentified_reason = "stuck"


def _record(state: Any, rule: str, action: Any = None) -> None:
    from ..decide.plan import Action, Say, TurnPlan, record

    owner = "diagnosis" if state.identity.customer_id else "identification"
    plan = TurnPlan(
        owner=owner, rule=rule, action=action or Action(type="none"), say=Say(kind="phrase")
    )
    record(state, plan)


def maybe_end_on_goodbye(state: Any, rt: Any, text: str) -> None:
    """Catch-all hang-up: if the agent JUST said a terminal goodbye — on ANY path
    (resolved, registered, declined, or the stuck backstop) — end the call so the
    transport stops instead of looping the goodbye. Covers the cases the
    case_closed/closing flow misses (e.g. the model says 'geros dienos' on a stuck
    turn without close_case ever firing)."""
    if state.closing.is_complete or not text:
        return
    low = text.lower()
    if any(m in low for m in vocab("goodbye_markers")):
        state.closing.is_complete = True


def commit_driven(state: Any, rt: Any, user_input: str | None, reply: str) -> str:
    """End-of-turn bookkeeping for a solver-led reply (the narrator's path does the same
    in begin_turn): the user_turn trace, the dialogue history, the shared finalisation."""
    from ..graph_v2.runtime import narrator

    if user_input:
        state.dialog.last_heard = user_input.strip()
        rt.tracer.emit("user_turn", text=user_input)
        state.messages.append({"role": "user", "content": user_input})
    state.messages.append({"role": "assistant", "content": reply})
    narrator(state, rt)._finalize_reply(reply)
    return reply
