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

from ...router import DIAGNOSIS
from ...runtime import DIAGNOSIS_NODE_PROMPT, narrate, sync_updates
from ...state import GraphState


def make_narrator_node(engine: Any):
    def narrator_node(state: GraphState) -> dict[str, Any]:
        user_input = state.turn.user_input
        reply = narrate(engine, user_input, None, DIAGNOSIS_NODE_PROMPT, DIAGNOSIS)
        engine._mark_step_presented()
        return sync_updates(engine, user_input=user_input, reply=reply)

    return narrator_node
