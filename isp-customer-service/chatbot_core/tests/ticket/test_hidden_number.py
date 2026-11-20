"""Paslėptas numeris (#80 — Andrius, 2026-11-20): a call with no caller ID was asked „Ar tiks
numeris, iš kurio skambinate?", and „tiks" put "unknown" on the ticket. Without a caller ID the
number is asked for; a „tiks" is no number; and the ticket never says "unknown".
"""

FUNCTION = "Paslėptas numeris"


def _asking(make_state, make_runtime, phone):
    from agent.decide.rules.ticket import ticket_stage_reply
    from agent.graph_v2.state import TicketContext

    state, rt = make_state(phone), make_runtime()
    state.ticket.stage, state.ticket.reason = "phone", "telefonu_nepataisoma"
    state.ticket.context = TicketContext()
    return state, rt, ticket_stage_reply(state, rt)


def test_a_hidden_number_is_asked_for(make_state, make_runtime):
    _, _, said = _asking(make_state, make_runtime, "unknown")
    assert "nerodomas" in said and "iš kurio skambinate" not in said


def test_a_shown_number_is_offered(make_state, make_runtime):
    _, _, said = _asking(make_state, make_runtime, "+37060020101")
    assert "iš kurio skambinate" in said


def test_tiks_is_no_number_when_it_is_hidden(make_state, make_runtime):
    from agent.decide.rules.ticket import ticket_capture, ticket_stage_reply

    state, rt, _ = _asking(make_state, make_runtime, "unknown")
    ticket_capture(state, rt, "Taip, tiks.")
    assert state.ticket.contact_phone is None and state.ticket.stage == "phone"
    assert "skaitmenimis" in ticket_stage_reply(state, rt)
    ticket_capture(state, rt, "+370 600 12345")
    assert state.ticket.contact_phone == "+37060012345" and state.ticket.stage == "hours"


def test_no_number_after_the_asks_says_so(make_state, make_runtime):
    from agent.decide.rules.ticket import ticket_capture, ticket_stage_reply
    from agent.execute.ticket import NO_NUMBER

    state, rt, _ = _asking(make_state, make_runtime, "unknown")
    for _ in range(3):
        ticket_capture(state, rt, "Tiks.")
        ticket_stage_reply(state, rt)
    assert state.ticket.contact_phone == NO_NUMBER and state.ticket.stage == "hours"


def test_the_default_contact_is_never_unknown(make_state):
    from agent.execute.ticket import NO_NUMBER, caller_id

    assert caller_id(make_state("unknown")) is None
    assert caller_id(make_state("")) is None
    assert caller_id(make_state("+37060020101")) == "+37060020101"
    assert NO_NUMBER != "unknown"
