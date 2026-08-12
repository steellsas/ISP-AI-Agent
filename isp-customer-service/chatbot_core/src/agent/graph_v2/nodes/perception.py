"""
Perception node — understand the caller's turn before anyone acts on it.

Migrates here (roadmap §4): ReactAgent._ingest_client_evidence,
understand.understand, ReactAgent.classify_side_topic,
ReactAgent._prefill_slots_from_text.

R4 upgrade: understand + intent + step-classifier merge into ONE fast
structured-output LLM call (latency -0.5..1.5 s per turn).
"""

from __future__ import annotations

from ..state import GraphState


def perception_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the legacy perception methods")
