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
    perceive(state, rt, state.turn.user_input)
    return node_update(state)


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
    ingest_client_evidence(state, rt, user_input)
    state.turn.side_topic_active = bool(classify_side_topic(state, rt, user_input))


def raise_clarity(state: Any, user_input: str | None) -> None:
    """Once the caller says they do not follow the wording ("kas tas WAN?"),
    stay in plain language for the rest of the call. One-way: a caller who was
    lost once should not be dropped back into jargon two steps later."""
    from .detectors import detect_confusion

    if state.dialog.clarity_level == "standard" and detect_confusion(user_input):
        state.dialog.clarity_level = "basic"
