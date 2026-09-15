"""
Identification node — address slots, lookup, caller confirmation.

R2 thin wrapper around the engine's address-validation turn —
lookup-only toolset, then _mark_step_presented (resolve_address may have
identified the caller mid-turn and the same reply narrates the first step).

R3 migrates here (roadmap §4): ReactAgent._identification_scripted_reply,
_reopen_identification, _preflight_phone, revalidate_accumulated_address.
Slot policy stays pure in agent/slots.py + agent/identification.py.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ...runtime import AgentRuntime
from ..router import ADDRESS_VALIDATION
from ..runtime import ADDRESS_NODE_PROMPT, LOOKUP_TOOLS, narrate, node_update
from ..state import GraphState


def identification_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ...narrator_flow import mark_step_presented

    rt = runtime.context
    state = state.model_copy(deep=True)

    def body() -> str:
        user_input = state.turn.user_input
        reply = narrate(
            state,
            rt,
            user_input,
            LOOKUP_TOOLS,
            ADDRESS_NODE_PROMPT,
            ADDRESS_VALIDATION,
        )
        mark_step_presented(state, rt)
        from ...decide.plan import record_stage_reply

        record_stage_reply(state, "identification.free_reply")
        return reply

    return node_update(state, body())
