"""The policy chain — an ordered list of rule families; the first plan wins (M4 §5).

Each rule reads the state the perceive node left and returns a TurnPlan or None. A rule
may write the dialogue bookkeeping it owns (counters, stages, flags on the state copy);
tools, ticket registration and speech are the plan's action and say, run after it.

The order ports today's precedence (docs/refactoring/M4_decide.md §5). Families not
ported yet still run in the stage nodes after the chain returns None — porting goes
top-down, so every ported family keeps its place ahead of the unported ones.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .plan import TurnPlan
from .rules import closing, dialog, head, intake, stage, ticket, tools

Rule = Callable[[Any, Any], TurnPlan | None]

# (§5 row, family, rule) — highest precedence first.
RULES: list[tuple[float, str, Rule]] = [
    (1, "dialog.greeting", dialog.greeting),
    (2, "closing", closing.plan),
    # A system that did not answer is news of its own: it plans the manifest's fallback
    # before the stage families plan around a check that never ran (wave 2c-4).
    (2.5, "tools.unavailable", tools.plan),
    (3, "ticket", ticket.plan),
    (4, "dialog.end_confirm_answer", head.head_rule(head.end_confirm_answer)),
    (5, "identification.reopen_confirm_answer", head.head_rule(head.reopen_confirm_answer)),
    (6, "dialog.cannot_now", head.head_rule(head.cannot_now_shield)),
    (7, "dialog.farewell_mid_process", head.head_rule(head.farewell_mid_process)),
    (8, "identification.caller_intro", head.head_rule(head.caller_intro)),
    (9, "identification", head.head_rule(head.unidentified_address)),
    (10, "identification.address_correction", head.head_rule(head.address_correction)),
    # Rows 11-20: the stage families (side topic, the inform close, the Case) plan the
    # rest; the dialogue scripts (rows 11-15, 18-19) come from the reply layer.
    # Row 13 (diagnosis.hypothesis_confirm) is gone with wave 3: the Case holds candidates,
    # so a single belief with a doubt/confirm state machine has nothing to confirm.
    (20, "stage", stage.plan),
]


def plan_turn(state: Any, rt: Any) -> TurnPlan | None:
    """The first rule family that owns this turn (the stage families always do).

    The turn's readings become the call's facts first (wave 1c): what perceive HEARD is a
    label, what the call is ABOUT is a decision.
    """
    intake.apply_readings(state, rt)
    for _row, _family, rule in RULES:
        plan = rule(state, rt)
        if plan is not None:
            return plan
    return None
