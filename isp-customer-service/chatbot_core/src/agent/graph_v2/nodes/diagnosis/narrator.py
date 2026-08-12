"""
Narrator node — the voice of the agent: one LLM streaming call per turn.

Migrates here (roadmap §4): ReactAgent._build_messages, _state_facts_block,
_run_until_response_stream, _scoped_tools_schema, repeat guard (_track_stuck,
_stuck_backstop). Token streaming goes out through langgraph
get_stream_writer(); barge-in cancellation (request_cancel) must reach this
node's LLM stream — verify at the end of R2 with a live voice call.

R5 upgrade: IT-specialist persona — expert explanations from fault packs,
confidence language, few-shot expert dialogues in stage prompts.
"""

from __future__ import annotations

from ...state import GraphState


def narrator_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the streaming narrator loop")
