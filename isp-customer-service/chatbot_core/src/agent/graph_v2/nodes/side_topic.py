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
from ..runtime import SIDE_TOPIC_PROMPT, narrate, run_on_state
from ..state import GraphState


def side_topic_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    engine = runtime.context.engine

    def body() -> str:
        user_input = state.turn.user_input
        return narrate(
            engine.state, engine.runtime, user_input, frozenset(), SIDE_TOPIC_PROMPT, SIDE_TOPIC
        )

    return run_on_state(engine, state, body)
