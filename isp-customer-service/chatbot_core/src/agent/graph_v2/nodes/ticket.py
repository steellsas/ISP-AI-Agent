"""
Ticket node — the scripted 2-question contact dialogue before registration.

R2 thin wrapper around the engine's ticket-registration turn —
the engine owns the dialogue (guards capture answers, the scripted ladder
asks, _finish_ticket_dialogue registers); the LLM (no tools) speaks only on
an off-script question.

R3 migrates here (roadmap §4): _begin/_finish_ticket_dialogue,
_ticket_stage_reply, _ticket_need, _abort_ticket_to_solving,
_wants_to_keep_solving; the dialogue context lives on GraphState.ticket.
"""

from __future__ import annotations

from typing import Any

from ..router import TICKET_REGISTRATION
from ..runtime import TICKET_NODE_PROMPT, TICKET_TOOLS, narrate, run_on_state
from ..state import GraphState


def make_ticket_node(engine: Any):
    def ticket_node(state: GraphState) -> dict[str, Any]:
        def body() -> str:
            user_input = state.turn.user_input
            return narrate(
                engine, user_input, TICKET_TOOLS, TICKET_NODE_PROMPT, TICKET_REGISTRATION
            )

        return run_on_state(engine, state, body)

    return ticket_node
