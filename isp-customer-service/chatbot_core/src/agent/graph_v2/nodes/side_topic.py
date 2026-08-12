"""
Side-topic node — a REAL node in v2 (today: a sub-call inside diagnosis).

Migrates here (roadmap §4): the frozen-engine side answer (FAQ facts, no
tools) + the mandatory verbatim anchor-question repeat; the 3rd consecutive
deviation goes scripted (back_to_issue / solve_or_ticket).
"""

from __future__ import annotations

from ..state import GraphState


def side_topic_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the legacy side-topic reply")
