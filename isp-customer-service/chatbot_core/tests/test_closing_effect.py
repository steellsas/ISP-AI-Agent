"""Wave 1b: a call ends in ONE place.

Twenty places used to write the closing flags by hand, and one could silently overwrite
another's reason. Now every path goes through `agent/closing.py::close_call`, the gate
validates the reason a plan carries, and nothing else touches the flags.
"""

import re
from pathlib import Path

import pytest
from agent.closing import close_call, hang_up
from agent.decide.gate import CLOSE_REASONS, check_plan
from agent.decide.plan import Action, Say, TurnPlan

_SRC = Path(__file__).resolve().parents[1] / "src" / "agent"

# (reason, complete) -> (case_closed, closed_reason, is_complete)
REASONS = [
    ("resolved", False, (True, "resolved", False)),
    ("registered", False, (True, "registered", False)),
    ("declined", True, (True, "declined", True)),
    ("callback", False, (True, "callback", False)),
    ("inform", False, (True, "inform", False)),
    ("outage", True, (True, "outage", True)),
]


@pytest.mark.parametrize("reason, complete, expected", REASONS)
def test_a_close_records_its_reason(reason, complete, expected, make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()

    close_call(state, rt, reason, complete=complete)

    got = (state.closing.case_closed, state.closing.closed_reason, state.closing.is_complete)
    assert got == expected


def test_keep_hangs_up_without_re_deciding_the_reason(make_state, make_runtime):
    """The farewell of an already closed case: it ends the CALL, not the case."""
    state, rt = make_state("+37060020112"), make_runtime()
    close_call(state, rt, "resolved")

    hang_up(state, rt)

    assert (state.closing.closed_reason, state.closing.is_complete) == ("resolved", True)


def test_the_stuck_close_keeps_the_promise_for_an_identified_caller(
    make_state, make_runtime, db_connection
):
    state, rt = make_state("+37060020112"), make_runtime()
    state.identity.customer_id = "CUST009"
    state.resolution.procedure = {"verdict": "router_hung", "step": "rh_check"}

    close_call(state, rt, "stuck", complete=True)

    assert state.ticket.ticket_id  # F-5
    assert state.closing.closed_reason == "registered"
    assert state.resolution.procedure["escalate_reason"] == "stuck"


def test_an_unknown_close_reason_is_gated(make_state, make_runtime):
    state, rt = make_state("+37060020112"), make_runtime()
    plan = TurnPlan(
        owner="closing",
        rule="closing.goodbye",
        action=Action(type="close", name="because-i-said-so"),
        say=Say(kind="phrase", text="Geros dienos!", stage="closing"),
    )

    gated = check_plan(state, rt, plan)

    assert gated.action.type == "none" and gated.rule.endswith(".gated")
    assert state.closing.case_closed is False


@pytest.mark.parametrize("reason", sorted(CLOSE_REASONS))
def test_every_gated_reason_is_implemented(reason, make_state, make_runtime):
    """A reason the gate accepts must do something — no silent no-ops."""
    state, rt = make_state("+37060020112"), make_runtime()
    if reason == "stuck":
        pytest.skip("covered by its own test (it registers a ticket)")

    close_call(state, rt, reason)

    assert state.closing.case_closed is True


def test_no_module_writes_the_closing_flags_itself():
    """The architectural guard: `closing.py` is the only writer. A new rule that closes
    a call must plan Action(type="close") (or call close_call), so the reason is traced
    and the gate can refuse it."""
    writers = set()
    pattern = re.compile(r"closing\.(case_closed|closed_reason)\s*=(?!=)")
    for path in _SRC.rglob("*.py"):
        if path.name == "closing.py":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if pattern.search(line):
                writers.add(f"{path.relative_to(_SRC).as_posix()}: {line.strip()}")

    # closing.py owns the flags; the closing rules may still REOPEN a case (a ticket
    # demand at the goodbye), which is a different write.
    assert {w for w in writers if "= False" not in w} == set()
