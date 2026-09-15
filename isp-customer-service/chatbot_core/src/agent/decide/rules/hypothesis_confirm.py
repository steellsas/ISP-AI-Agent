"""The answer to the hypothesis confirm question (§5 row 13, D-05).

A telemetry recheck named another cause and the caller was asked about its symptom:
yes -> the belief changes and the new procedure starts; no -> the belief stays and the
old procedure ends in its registration; unclear -> the question is asked once more,
then treated as no. The answer never doubles as a step answer (the procedure holds
this turn).
"""

from __future__ import annotations

from typing import Any

from ...contract import limits


def plan(state: Any, rt: Any) -> None:
    from ...perceive.detectors import detect_yes_no
    from ...resolution import Outcome
    from .. import hypothesis

    c = state.diagnosis.contradiction
    user_input = state.turn.user_input
    if c is None or c.kind != "verdict" or not c.asked or not user_input:
        return None
    answer = detect_yes_no(user_input)
    state.dialog.resume_hold_due = True  # the answer belongs to the confirm question
    if answer is Outcome.YES:
        hypothesis.answered(state, rt, "verdict")
        hypothesis.change_confirmed(state, rt, c)
        return None
    c.asks += 1
    if answer is None and c.asks < limits.get("hypothesis_confirm_max_asks"):
        c.asked = False  # the question is due again
        rt.tracer.emit("hypothesis", status="doubt", kind="verdict", reask=True)
        return None
    hypothesis.answered(state, rt, "verdict")
    from ..procedure import goto_role

    r = state.resolution.procedure or {}
    goto_role(state, rt, r, "escalate")
    rt.tracer.emit("hypothesis", status="kept", kind="verdict", before=c.before_value)
    return None
