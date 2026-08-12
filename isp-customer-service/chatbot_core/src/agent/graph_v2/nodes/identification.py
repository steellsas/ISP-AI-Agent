"""
Identification node — address slots, lookup, caller confirmation.

Migrates here (roadmap §4): ReactAgent._identification_scripted_reply,
_reopen_identification, _preflight_phone, _revalidate_accumulated_address.
Slot policy stays pure in agent/slots.py + agent/identification.py.
"""

from __future__ import annotations

from ..state import GraphState


def identification_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over the legacy identification flow")
