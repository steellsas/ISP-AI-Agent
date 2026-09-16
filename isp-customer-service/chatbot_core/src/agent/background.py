"""Work done between turns, while the caller is busy.

A READ-ONLY telemetry refresh runs in the voice layer's background thread; its result
waits in the session inbox and is folded in at the START of the next turn, never
mid-reply. Speculation (precomputed branch replies) was removed in M5 — latency is
reviewed again after M7.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any


def apply_bg_diagnosis(state: Any, rt: Any) -> None:
    """Fold the background telemetry read in ONLY as a refresh — in the solution/bridge
    phase, or when the fresh verdict FLIPS the story, it is discarded (the solution steps
    read at the right moments themselves; live: the bg read saw the just-plugged PC, the
    narrative turned foreign_mac mid-bridge and the agent asked "ar keitėte routerį?"
    over a working bind)."""
    from .narrator_flow import update_state_from_observation

    bg = state.turn.bg_diagnosis
    if not bg:
        return
    state.turn.bg_diagnosis = None
    # A-2R (2026-09-07): with no identified customer the telemetry has no
    # one to belong to — after reopen it used to restore the dropped
    # account's diagnosis.
    if not state.identity.customer_id:
        return
    with contextlib.suppress(Exception):
        r0 = state.resolution.procedure or {}
        in_solution = bool(
            r0.get("solution_synced")
            or state.resolution.bridge_plug_reported
            or state.resolution.bridge_bound
        )
        fresh = ((json.loads(bg) or {}).get("verdict") or {}).get("reason")
        current = r0.get("verdict")
        if not in_solution and (not current or fresh == current):
            update_state_from_observation(state, rt, "diagnose_connection", bg)
            rt.tracer.emit("telemetry_refresh", action="applied")
        else:
            rt.tracer.emit("telemetry_refresh", action="discarded", fresh=fresh)
