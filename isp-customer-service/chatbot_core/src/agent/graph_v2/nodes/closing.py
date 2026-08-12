"""
Closing node — one short goodbye matched to closed_reason, then hang-up.

R2 thin wrapper: ports closing() from agent/graph.py verbatim — _maybe_finish
decides whether to hang up (farewell or second closing turn sets is_complete)
BEFORE the tools-less narration.

R3 migrates here (roadmap §4): _maybe_close_inform, _maybe_end_on_goodbye,
end_session (call record + persistence).
"""

from __future__ import annotations

from typing import Any

from ..router import CLOSING
from ..runtime import CLOSING_NODE_PROMPT, CLOSING_TOOLS, narrate, sync_updates
from ..state import GraphState


def make_closing_node(engine: Any):
    def closing_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        engine._maybe_finish(user_input)
        reply = narrate(engine, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
        return sync_updates(engine, user_input=user_input, reply=reply)

    return closing_node
