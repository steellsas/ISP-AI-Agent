"""
Side-topic node — the frozen-engine deviation answer inside diagnosis.

The engine is already frozen for this turn (classify_side_topic returned True
in the diagnose node): no tools, the LLM answers ONLY from the FAQ facts and
must end by repeating the anchor question verbatim. The 3rd consecutive
deviation is a scripted frame composed in the engine.
"""

from __future__ import annotations

from typing import Any

from ..router import SIDE_TOPIC
from ..runtime import SIDE_TOPIC_PROMPT, narrate, sync_updates
from ..state import GraphState


def make_side_topic_node(engine: Any):
    def side_topic_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        reply = narrate(engine, user_input, frozenset(), SIDE_TOPIC_PROMPT, SIDE_TOPIC)
        return sync_updates(engine, user_input=user_input, reply=reply)

    return side_topic_node
