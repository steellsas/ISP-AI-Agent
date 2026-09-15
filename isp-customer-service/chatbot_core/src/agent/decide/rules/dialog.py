"""Dialog rules that belong to no stage (§5 rows 1, 4, 6, 7, 11, 18, 19, 20)."""

from __future__ import annotations

from typing import Any

from ..plan import Action, Say, TurnPlan


def greeting(state: Any, rt: Any) -> TurnPlan | None:
    """The first turn has no caller words: the fixed opening line, with the caller's
    number looked up while it plays."""
    if state.turn.user_input is not None or state.dialog.turn_count != 0:
        return None
    state.dialog.turn_count += 1  # the opening line is the call's first turn
    return TurnPlan(
        owner="intake",
        rule="dialog.greeting",
        action=Action(type="tool", name="preflight_phone"),
        say=Say(
            kind="phrase",
            key="system.greeting",
            vars={"company_name": rt.config.company_name},
            stage="intake",
            remember_question=False,
        ),
    )
