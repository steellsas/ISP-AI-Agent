"""
Identification node — address slots, lookup, caller confirmation.

R2 thin wrapper: ports address_validation() from agent/graph.py verbatim —
lookup-only toolset, then _mark_step_presented (resolve_address may have
identified the caller mid-turn and the same reply narrates the first step).

R3 migrates here (roadmap §4): ReactAgent._identification_scripted_reply,
_reopen_identification, _preflight_phone, _revalidate_accumulated_address.
Slot policy stays pure in agent/slots.py + agent/identification.py.
"""

from __future__ import annotations

from typing import Any

from ..router import ADDRESS_VALIDATION
from ..runtime import ADDRESS_NODE_PROMPT, LOOKUP_TOOLS, narrate, sync_updates
from ..state import GraphState


def make_identification_node(engine: Any):
    def identification_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        reply = narrate(engine, user_input, LOOKUP_TOOLS, ADDRESS_NODE_PROMPT, ADDRESS_VALIDATION)
        engine._mark_step_presented()
        return sync_updates(engine, user_input=user_input, reply=reply)

    return identification_node
