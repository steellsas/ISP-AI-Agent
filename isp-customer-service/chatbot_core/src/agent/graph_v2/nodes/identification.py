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
from ..runtime import ADDRESS_NODE_PROMPT, LOOKUP_TOOLS, narrate, run_on_state
from ..state import GraphState


def identification_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ...narrator_flow import mark_step_presented

    engine = runtime.context.engine

    def body() -> str:
        user_input = state.turn.user_input
        reply = narrate(
            engine.state,
            engine.runtime,
            user_input,
            LOOKUP_TOOLS,
            ADDRESS_NODE_PROMPT,
            ADDRESS_VALIDATION,
        )
        mark_step_presented(engine.state, engine.runtime)
        return reply

    return run_on_state(engine, state, body)
