"""
Evidence-drive node — declarative fault questioning from faults.yaml.

Migrates here (roadmap §4): ReactAgent._evidence_drive, _maybe_facts_recap,
_maybe_refute_confirm, _revive_gave_up_key, _negation_clarify_reply. Ledger
mechanics (set_fact, hypothesis_status, next_missing, solution_for) stay pure
in agent/evidence.py.
"""

from __future__ import annotations

from ...state import GraphState


def evidence_drive_node(state: GraphState) -> GraphState:
    raise NotImplementedError("R2: thin wrapper over _evidence_drive")
