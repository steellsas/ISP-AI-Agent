"""
Narrator node — the voice of the diagnosis stage: one streaming LLM turn.

Thin wrapper over the scoped narration (full toolset, diagnosis stage prompt)
+ _mark_step_presented (the reply narrated the step's question, so the
caller's next answer may advance the walker) + the engine-state sync.

R5 upgrade: IT-specialist persona — expert explanations from fault packs,
confidence language, few-shot expert dialogues in stage prompts.
"""

from __future__ import annotations

from typing import Any

from langgraph.runtime import Runtime

from ....runtime import AgentRuntime
from ...router import DIAGNOSIS
from ...runtime import DIAGNOSIS_NODE_PROMPT, narrate, node_update
from ...state import GraphState


def narrator_node(state: GraphState, runtime: Runtime[AgentRuntime]) -> dict[str, Any]:
    from ....narrator_flow import mark_step_presented

    rt = runtime.context
    state = state.model_copy(deep=True)

    def body() -> str:
        user_input = state.turn.user_input
        reply = narrate(state, rt, user_input, None, DIAGNOSIS_NODE_PROMPT, DIAGNOSIS)
        mark_step_presented(state, rt)
        return reply

    return node_update(state, body())
