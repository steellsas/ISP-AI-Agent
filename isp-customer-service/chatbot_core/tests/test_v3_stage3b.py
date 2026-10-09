"""STRUKTURA_V3 stage 3b — one owner for the ending, one for the registration.

Before: about twelve places wrote the closing flags and eleven started the contact dialogue,
each its own way; a guard added to one never reached the others (S1-S7, wave 9). These tests
keep it that way: the flags are written only in `agent/closing.py`, and the dialogue starts
only through `execute.ticket.request_ticket`.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "agent"
_CLOSING_WRITE = re.compile(r"\bclosing\.(case_closed|is_complete|closed_reason)\s*=[^=]")


def _sources():
    for path in SRC.rglob("*.py"):
        yield path, path.read_text(encoding="utf-8")


def test_only_the_closing_module_writes_the_closing_flags():
    writers = [
        f"{path.relative_to(SRC)}:{n}"
        for path, text in _sources()
        if path.name != "closing.py" or path.parent != SRC
        for n, line in enumerate(text.splitlines(), 1)
        if _CLOSING_WRITE.search(line)
    ]
    assert writers == []


def test_the_contact_dialogue_starts_only_through_request_ticket():
    callers = [
        f"{path.relative_to(SRC)}:{n}"
        for path, text in _sources()
        for n, line in enumerate(text.splitlines(), 1)
        if "_begin_ticket_dialogue(" in line
        and "def _begin_ticket_dialogue" not in line
        and path.relative_to(SRC).as_posix() != "execute/ticket.py"
    ]
    assert callers == []


class _Tracer:
    session_id = "3b"

    def __init__(self):
        self.events = []

    def emit(self, event_type, **fields):
        self.events.append({"type": event_type, **fields})


@pytest.fixture
def call(make_state, make_runtime):
    tracer = _Tracer()
    state, rt = make_state("+37060012353"), make_runtime(tracer=tracer)
    state.identity.customer_id = "CUST009"
    return state, rt, tracer


def test_a_fault_ticket_carries_its_card_note_and_its_reason(call):
    from agent.execute.ticket import request_ticket

    state, rt, tracer = call
    state.case.fault, state.case.solution = "no_mac_observed", 0
    request_ticket(state, rt, "case_escalate")

    assert state.ticket.stage == "phone"
    assert state.case.facts.get("_ticket_note")  # the card's note for the technician
    asked = [e for e in tracer.events if e.get("intent") == "ticket_requested"]
    assert asked and asked[0]["action"] == "case_escalate"


def test_a_request_is_typed_and_a_running_one_is_not_restarted(call):
    from agent.execute.ticket import request_ticket

    state, rt, tracer = call
    request_ticket(state, rt, "request", request_type="billing_request")
    request_ticket(state, rt, "promise")  # already collecting — nothing changes

    assert state.ticket.request_type == "billing_request"
    assert len([e for e in tracer.events if e.get("intent") == "ticket_requested"]) == 1


def test_reopening_clears_the_end(call):
    from agent.closing import close_call, reopen_call

    state, rt, _ = call
    close_call(state, rt, "resolved", complete=True)
    reopen_call(state, rt, "still_down")

    assert not state.closing.case_closed and not state.closing.is_complete
