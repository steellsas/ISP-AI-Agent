"""
Ticket node — the scripted 2-question contact dialogue before registration.

Migrates here (roadmap §4): ReactAgent._begin/_finish_ticket_dialogue,
_ticket_stage_reply, _ticket_need, _abort_ticket_to_solving,
_wants_to_keep_solving. Ticket creation itself stays deterministic in the
executor (register from STATE, never by the model).

R3 note: _ticket_stage / _ticket_ctx are promoted to GraphState fields
(they outlive a turn — roadmap §6).
"""

from __future__ import annotations

from ..state import GraphState


def ticket_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the legacy ticket dialogue")
