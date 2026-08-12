"""
Ticket node — the scripted 2-question contact dialogue before registration.

R2 thin wrapper: ports ticket_registration() from agent/graph.py verbatim —
the engine owns the dialogue (guards capture answers, the scripted ladder
asks, _finish_ticket_dialogue registers); the LLM (no tools) speaks only on
an off-script question.

R3 migrates here (roadmap §4): _begin/_finish_ticket_dialogue,
_ticket_stage_reply, _ticket_need, _abort_ticket_to_solving,
_wants_to_keep_solving; _ticket_ctx promotes to GraphState.
"""

from __future__ import annotations

from typing import Any

from ..router import TICKET_REGISTRATION
from ..runtime import TICKET_NODE_PROMPT, TICKET_TOOLS, narrate, sync_updates
from ..state import GraphState


def make_ticket_node(engine: Any):
    def ticket_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        reply = narrate(engine, user_input, TICKET_TOOLS, TICKET_NODE_PROMPT, TICKET_REGISTRATION)
        return sync_updates(engine, user_input=user_input, reply=reply)

    return ticket_node
