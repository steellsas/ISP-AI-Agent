"""
Diagnose node — telemetry read + verdict on stage entry / re-diagnosis.

Migrates here (roadmap §4): ReactAgent.ensure_diagnosed, _refresh_diagnosis,
_fresh_diagnose_reason. The verdict tree itself stays pure in agent/verdict.py.
"""

from __future__ import annotations

from ...state import GraphState


def diagnose_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over ensure_diagnosed")
