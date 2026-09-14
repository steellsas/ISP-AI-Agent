"""
Side-topic node — the frozen-engine deviation answer inside diagnosis.

The engine is already frozen for this turn (classify_side_topic returned True
in the diagnose node): no tools, the LLM answers ONLY from the FAQ facts and
must end by repeating the anchor question verbatim. The 3rd consecutive
deviation is a scripted frame composed in the engine.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ...runtime import AgentRuntime
from ..router import SIDE_TOPIC
from ..runtime import SIDE_TOPIC_PROMPT, narrate, node_update
from ..state import GraphState


def side_topic_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    rt = runtime.context
    state = state.model_copy(deep=True)

    def body() -> str:
        user_input = state.turn.user_input
        return narrate(state, rt, user_input, frozenset(), SIDE_TOPIC_PROMPT, SIDE_TOPIC)

    return node_update(state, body())
