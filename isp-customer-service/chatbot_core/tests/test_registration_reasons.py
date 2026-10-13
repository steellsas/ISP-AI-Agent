"""Registration only for a written-down reason, decided by the engine (Andrius, 2026-10-13).

`knowledge/registracija.yaml` is the one list of WHEN a ticket is registered. The engine starts
a registration through `request_ticket(state, rt, <reason>)` (or `registration.mark` for one that
skips the contact dialogue) and nothing else — a model's word never does.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "agent"
_CALL = re.compile(r"""(?:request_ticket\([^)]*?|mark\(\s*\w+\s*,)\s*["']([a-z_]+)["']""")


def _reasons_in_code() -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        found |= set(_CALL.findall(path.read_text(encoding="utf-8")))
    for path in SRC.rglob("case_rule.py"):
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'_escalate\([^)]*?why="([a-z_]+)"', text, re.S))
    return found


def test_every_reason_in_the_code_is_written_down():
    from agent.contract.registration import reasons

    used = _reasons_in_code()
    assert used, "the scan found no registration at all"
    assert used <= set(reasons()), f"not in registracija.yaml: {used - set(reasons())}"


def test_every_reason_says_when_and_why():
    from agent.contract.registration import reasons

    for key, spec in reasons().items():
        assert spec.get("kada") and spec.get("tiketui"), key
        assert spec.get("sutikimas") in ("taip", "ne"), key


def test_an_unknown_reason_is_refused(make_state, make_runtime):
    from agent.contract.schema import KnowledgeError
    from agent.execute.ticket import request_ticket

    state, rt = make_state("+37060012353"), make_runtime()
    with pytest.raises(KnowledgeError):
        request_ticket(state, rt, "promise")  # the model's word is not a reason


def test_the_reason_goes_onto_the_ticket(make_state, make_runtime):
    from agent.executor_flow import register_ticket_from_state

    from tests.calls import make_runtime as runtime_with

    created = []

    def tools(name, args):
        if name == "create_ticket":
            created.append(args)
            return {"success": True, "ticket_id": "T"}
        return {}

    state = make_state("+37060012353")
    rt = runtime_with(fake_tools=tools)
    state.identity.customer_id = "CUST009"
    state.case.fault = "no_mac_observed"
    state.ticket.reason = "telefonu_nepataisoma"
    register_ticket_from_state(state, rt)

    assert (
        "Registruota, nes: gedimo telefonu pašalinti negalima."
        in (created[0]["problem_description"])
    )


def test_the_card_offers_no_registration():
    """The dialogue lines used to tell the model to „offer to register the fault" — a decision
    the engine had not made."""
    card = (SRC / "speak" / "context_card.py").read_text(encoding="utf-8")
    for offer in (
        "or offer to register the fault",
        "register the problem for a call-back",
        "you will register a technician",
    ):
        assert offer not in card, offer
    assert card.count("Promise no registration") >= 2  # what the lines say instead
