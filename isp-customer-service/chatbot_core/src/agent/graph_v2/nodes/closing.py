"""
Closing node — one short goodbye matched to closed_reason, then hang-up.

Migrates here (roadmap §4): ReactAgent._maybe_finish, _maybe_close_inform,
_maybe_end_on_goodbye, end_session (call record + persistence).
"""

from __future__ import annotations

from ..state import GraphState


def closing_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the legacy closing flow")
