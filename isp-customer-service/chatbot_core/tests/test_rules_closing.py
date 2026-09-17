"""Closing rules (§5 row 2): state + caller words -> the plan's rule id."""

import pytest
from agent.decide.rules import closing, dialog
from agent.graph_v2.state import ClosingState, TicketState, TurnScratch


def _state(make_state, text, **groups):
    groups.setdefault("closing", ClosingState(case_closed=True))
    return make_state("+37060012353", turn=TurnScratch(user_input=text), **groups)


@pytest.mark.parametrize(
    ("text", "groups", "rule"),
    [
        ("Užregistruokit gedimą", {"procedure": True}, "closing.ticket_demand_reopen"),
        (
            "Internetas neveikia",
            {
                "procedure": True,
                "closing": ClosingState(case_closed=True, closed_reason="resolved"),
            },
            "closing.still_down_reopen",
        ),
        (
            "Skambinkite kitu numeriu 868321007",
            {"ticket": TicketState(ticket_id="TCK-1")},
            "closing.ticket_phone_amend",
        ),
        ("Gerai, ačiū", {"ticket": TicketState(ticket_id="TCK-1")}, "closing.goodbye_after_ticket"),
        ("Gerai", {}, "closing.goodbye"),
        ("O kiek tai kainuos?", {}, "closing.free_reply"),
    ],
)
def test_closing_rule(make_state, make_runtime, text, groups, rule):
    procedure = groups.pop("procedure", False)
    state = _state(make_state, text, **groups)
    if procedure:
        state.resolution.procedure = {"verdict": "router_hung", "step": "rh_check"}
    plan = closing.plan(state, make_runtime())
    assert plan is not None and plan.rule == rule and plan.owner == "closing"


def test_open_case_is_not_the_closing_rules(make_state, make_runtime):
    state = make_state("+37060012353", turn=TurnScratch(user_input="Gerai"))
    assert closing.plan(state, make_runtime()) is None


def test_greeting_only_on_the_first_turn(make_state, make_runtime):
    rt = make_runtime()
    first = make_state("+37060012353")
    plan = dialog.greeting(first, rt)
    assert plan.rule == "dialog.greeting" and plan.action.name == "preflight_phone"
    assert first.dialog.turn_count == 1
    assert dialog.greeting(first, rt) is None
