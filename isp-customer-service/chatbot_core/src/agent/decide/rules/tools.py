"""A tool that did not answer decides the turn (wave 2c-4).

The gateway leaves the failure on the turn (`turn.tool_failure`) with the plan its manifest
declared; this rule carries that plan out ONCE:

    ask_client  the line is invisible to us now -> say so and keep asking the caller
                (the evidence ladder already knows how to work without telemetry)
    ticket      we cannot fix it remotely -> start the contact dialogue for a technician
    end_call    the register itself is down -> say so and end politely
    skip        nothing to say; the call goes on

Only `end_call` owns the turn outright. The other fallbacks let the normal families plan as
they would, and the card tells the narrator what happened — so the reply never claims a
check that never ran.
"""

from __future__ import annotations

from typing import Any

from ..plan import Action, Say, TurnPlan


def plan(state: Any, rt: Any) -> TurnPlan | None:
    """The manifest's fallback, applied once per failure."""
    failure = state.turn.tool_failure
    if not failure:
        return None
    state.turn.tool_failure = None  # handled: the redecide loop must not spin on it
    state.turn.tool_trouble = failure
    fallback = failure.get("fallback")
    rt.tracer.emit(
        "tool_fallback",
        tool=failure.get("tool"),
        capability=failure.get("capability"),
        error=failure.get("error"),
        fallback=fallback,
    )
    if fallback == "ticket":
        from ...execute.ticket import begin_ticket_dialogue

        begin_ticket_dialogue(state, rt, None)  # contacts first, then register + close
        return None
    if fallback == "end_call":
        return TurnPlan(
            owner="closing",
            rule="tools.systems_down",
            # "stuck" is the backstop's close: an identified caller still gets the
            # registration they were promised, an unidentified one is recorded as stuck.
            action=Action(type="close", name="stuck"),
            say=Say(kind="phrase", key=failure.get("say_key"), stage="closing"),
        )
    return None  # ask_client / skip: the stage families plan, the card carries the news
