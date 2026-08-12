"""
Closing node — one short goodbye matched to closed_reason, then hang-up.

maybe_finish (agent/closing_flow.py, R3 extraction) decides whether to hang
up (farewell or second closing turn sets is_complete) BEFORE the tools-less
narration.

R3 follow-up (roadmap §4): end_session (call record + persistence).
"""

from __future__ import annotations

from typing import Any

from ...closing_flow import maybe_finish
from ..router import CLOSING
from ..runtime import CLOSING_NODE_PROMPT, CLOSING_TOOLS, narrate, sync_updates
from ..state import GraphState


def make_closing_node(engine: Any):
    def closing_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        maybe_finish(engine, user_input)
        reply = narrate(engine, user_input, CLOSING_TOOLS, CLOSING_NODE_PROMPT, CLOSING)
        return sync_updates(engine, user_input=user_input, reply=reply)

    return closing_node
