"""
Perceive node — the first node of every turn: it reads, it never decides.

It may write facts, slots, the understanding pass, the side-topic signal and the
clarity level. It never closes the call, starts or ends the ticket dialogue, moves
the procedure, commits an identity or says anything — those are decisions that come
after it.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ..graph_v2.runtime import node_update
from ..graph_v2.state import GraphState
from ..runtime import AgentRuntime


def perceive_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)
    apply_background_signals(state, rt)
    read_turn_start(state, rt, state.turn.user_input)
    perceive(state, rt, state.turn.user_input)
    return node_update(state)


def read_turn_start(state: Any, rt: Any, user_input: str | None) -> None:
    """What the caller said, before anything reads it further: the heard text and turn
    intent, the background telemetry fold, and the utterance on the history.

    Wave 1: this ran in the speaker (speak.begin_turn), i.e. AFTER the turn was
    decided — so the scripted families could not be decided from it. Reading belongs
    to perceive.
    """
    from ..background import apply_bg_diagnosis
    from .detectors import detect_turn_intent

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


def apply_background_signals(state: Any, rt: Any) -> None:
    """The analyst's background read (voice) lands on the call state here, at the
    start of the turn — the deciding signals reach the decisions of THIS turn and the
    tone ones the reply."""
    raw = state.turn.analyst_signals
    if not raw:
        return
    from ..analyst.node import apply
    from ..analyst.signals import Signal

    apply(state, rt, [Signal(**item) for item in raw])
    state.turn.analyst_signals = None


def perceive(state: Any, rt: Any, user_input: str | None) -> None:
    """Read one caller turn into the state (no-op for the greeting turn)."""
    from ..dialog_utils import progress_key
    from .evidence import ingest_client_evidence
    from .node import raise_clarity
    from .perception import read_turn
    from .side_topic import classify_side_topic
    from .slots import prefill_slots_from_text

    if user_input is None:
        return
    # The repeat guard compares the progress at the end of the turn with this
    # snapshot — taken BEFORE the slots below are filled, so a slot heard this turn
    # counts as progress.
    state.turn.progress_key_at_start = progress_key(state)
    raise_clarity(state, user_input)
    if user_input:
        prefill_slots_from_text(state, rt, user_input)
    # THE reading of this turn (facts, the step answer, the ticket answer, the problem
    # label) — everything below consumes it.
    read_turn(state, rt, user_input)
    ingest_client_evidence(state, rt, user_input)
    # Wave 3: the facts the reader settled are the Case's facts.
    from ..ledger import mirror_evidence

    mirror_evidence(state, rt)
    state.turn.side_topic_active = bool(classify_side_topic(state, rt, user_input))


def raise_clarity(state: Any, user_input: str | None) -> None:
    """Once the caller says they do not follow the wording ("kas tas WAN?"),
    stay in plain language for the rest of the call. One-way: a caller who was
    lost once should not be dropped back into jargon two steps later."""
    from .detectors import detect_confusion

    if state.dialog.clarity_level == "standard" and detect_confusion(user_input):
        state.dialog.clarity_level = "basic"
