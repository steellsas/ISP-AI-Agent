"""A number said after „Užregistravau" lands on the ticket only once it is read back and the
caller confirms it — the same read-back as in the contact dialogue."""

import sqlite3

import pytest
from agent.db_path import database_path
from agent.graph_v2.state import ClosingState, GraphState, TicketContext, TicketState, TurnScratch
from langgraph.runtime import Runtime

from tests.calls import run_turn_nodes

FUNCTION = "Numeris po registracijos"

OWN = "+37060012353"
NEW = "868321007"


def _registered(make_state, **ctx):
    return make_state(
        OWN,
        ticket=TicketState(
            ticket_id="TCK-1",
            contact_phone=OWN,
            context=TicketContext(**ctx) if ctx else None,
        ),
        closing=ClosingState(case_closed=True, closed_reason="registered"),
    )


class _Call:
    """Closing turns on a registered call: decide -> execute -> narrate, tools faked."""

    def __init__(self, make_state, make_runtime, **ctx):
        self.rt = make_runtime(lambda name, args: {"success": True})
        self.state = _registered(make_state, **ctx)
        self.rule = None

    def say(self, text):
        self.state.turn = TurnScratch(user_input=text)
        events = []
        emit = self.rt.tracer.emit
        self.rt.tracer.emit = lambda event, **f: (events.append((event, f)), emit(event, **f))
        try:
            upd = run_turn_nodes(self.state, Runtime(context=self.rt))
        finally:
            self.rt.tracer.emit = emit
        self.state = GraphState(**upd)
        self.rule = next((f.get("rule") for e, f in events if e == "policy"), None)
        return self.state.turn.reply or ""

    @property
    def notes(self):
        return [
            args["note"]
            for name, args in self.rt.tools.provider.calls
            if name == "append_ticket_note"
        ]

    @property
    def pending(self):
        ctx = self.state.ticket.context
        return ctx.phone_pending if ctx else None


@pytest.fixture
def closing_call(make_state, make_runtime):
    return lambda **ctx: _Call(make_state, make_runtime, **ctx)


def test_a_new_number_is_read_back_first(closing_call):
    """Naujas numeris → perklausimas, į tiketą dar nerašoma"""
    c = closing_call()
    reply = c.say(f"Skambinkite kitu numeriu {NEW}")
    assert c.rule == "closing.ticket_phone_confirm"
    assert f"Užrašiau {NEW}" in reply
    assert c.notes == [] and c.state.ticket.contact_phone == OWN
    assert c.pending == NEW and not c.state.closing.is_complete


@pytest.mark.parametrize("answer", ["Taip", "Taip, teisingai", NEW, "8 683 21007"])
def test_a_yes_or_the_same_number_lands_on_the_ticket(closing_call, answer):
    """„Taip“ / tas pats numeris → pastaba + contact_phone"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    reply = c.say(answer)
    assert c.rule == "closing.ticket_phone_amend"
    assert "Užsirašiau" in reply
    assert len(c.notes) == 1 and NEW in c.notes[0] and "nepatvirtint" not in c.notes[0]
    assert c.state.ticket.contact_phone == NEW
    assert c.pending is None


def test_a_no_asks_again_and_writes_nothing(closing_call):
    """„Ne“ → klausiama iš naujo, pastabos nėra; naujas numeris perskaitomas"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    reply = c.say("Ne")
    assert c.rule == "closing.ticket_phone_reask"
    assert "pasakykite numerį dar kartą" in reply
    assert c.notes == [] and c.state.ticket.contact_phone == OWN
    reply = c.say("868321008")
    assert c.rule == "closing.ticket_phone_confirm" and "Užrašiau 868321008" in reply
    c.say("Taip")
    assert c.state.ticket.contact_phone == "868321008" and len(c.notes) == 1


def test_no_number_after_the_reask_leaves_the_ticket_as_it_was(closing_call):
    """Po „pasakykite dar kartą“ ne numeris → nieko nerašoma, atsisveikinama"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    c.say("Ne")
    c.say("Gerai, nesvarbu")
    assert c.notes == [] and c.state.ticket.contact_phone == OWN and c.pending is None
    assert c.rule == "closing.goodbye_after_ticket" and c.state.closing.is_complete


@pytest.mark.parametrize("number", ["860012353", OWN])
def test_the_number_already_on_the_ticket_changes_nothing(closing_call, number):
    """Numeris = caller ID / esamas contact_phone → nei pastabos, nei perklausimo"""
    c = closing_call()
    c.say(f"Skambinkite numeriu {number}")
    assert c.rule != "closing.ticket_phone_confirm"
    assert c.notes == [] and c.state.ticket.contact_phone == OWN and c.pending is None


def test_a_new_number_equal_to_the_ticket_contact_at_the_read_back_changes_nothing(closing_call):
    """Per perklausimą pasakytas esamas numeris → be pastabos"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    c.say("Ne, 860012353")
    assert c.notes == [] and c.state.ticket.contact_phone == OWN and c.pending is None


def test_a_question_keeps_the_read_back_open(closing_call):
    """Klausimas per perklausimą → atsako LLM, kitas „Taip“ vis dar priimamas"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    c.say("O kada atvažiuos meistras?")
    assert c.rule == "closing.free_reply"
    assert c.notes == [] and c.pending == NEW and not c.state.closing.is_complete
    c.say("Taip")
    assert c.rule == "closing.ticket_phone_amend" and c.state.ticket.contact_phone == NEW


def test_a_goodbye_at_the_read_back_notes_the_number_unconfirmed(closing_call):
    """Atsisveikinimas per perklausimą → pastaba „nepatvirtintas“, contact_phone nekeičiamas"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    from agent.call_record.finalizer import finalize

    c.say("Ačiū, viso gero")
    assert c.rule == "closing.goodbye_after_ticket" and c.state.closing.is_complete
    assert c.notes == []  # the call's end writes it, once
    finalize(c.state, c.rt, transport_end="client_closed")
    assert len(c.notes) == 1 and NEW in c.notes[0] and "nepatvirtint" in c.notes[0]
    assert c.state.ticket.contact_phone == OWN


def test_an_unclear_answer_repeats_the_read_back_once(closing_call):
    """Neaiškus atsakymas → perklausimas 1 kartą, antrą kartą → klausiama iš naujo"""
    c = closing_call()
    c.say(f"Skambinkite kitu numeriu {NEW}")
    assert f"Užrašiau {NEW}" in c.say("Kažkas trukdo")
    assert c.rule == "closing.ticket_phone_confirm"
    assert "pasakykite numerį dar kartą" in c.say("Hmm, kažkas")
    assert c.rule == "closing.ticket_phone_reask" and c.notes == []


def test_a_number_with_a_goodbye_is_read_back_not_hung_up(closing_call):
    """„Skambinkit 868…, viso gero“ → perklausimas, ragelis nepakabinamas"""
    c = closing_call()
    c.say(f"Skambinkite numeriu {NEW}, viso gero")
    assert c.rule == "closing.ticket_phone_confirm"
    assert not c.state.closing.is_complete and c.pending == NEW


def test_a_number_on_the_second_closing_turn_is_read_back(closing_call):
    """Numeris po klausimo (2-as closing ėjimas) → perklausimas, ne ragelis"""
    c = closing_call()
    c.say("O kada atvažiuos meistras?")
    c.say(f"Skambinkite kitu numeriu {NEW}")
    assert c.rule == "closing.ticket_phone_confirm" and not c.state.closing.is_complete


def test_a_hang_up_at_the_read_back_notes_the_number_unconfirmed(make_state, make_runtime):
    """Padėtas ragelis per perklausimą → pastaba „nepatvirtintas“"""
    from agent.call_record.finalizer import finalize

    rt = make_runtime(lambda name, args: {"success": True})
    state = _registered(make_state, phone_pending=NEW, phone_confirm_out=True)
    finalize(state, rt, transport_end="client_closed")
    notes = [a["note"] for n, a in rt.tools.provider.calls if n == "append_ticket_note"]
    assert len(notes) == 1 and NEW in notes[0] and "nepatvirtint" in notes[0]
    assert state.ticket.contact_phone == OWN


# --- the whole call: the real graph and the real ticket row ------------------------------


def _details(ticket_id):
    conn = sqlite3.connect(database_path())
    try:
        return conn.execute(
            "SELECT details FROM tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _registered_call(at_contacts):
    c = at_contacts()
    c.say("Taip")
    c.say("Po pietų")
    assert c.state.ticket.ticket_id
    return c


def test_a_confirmed_number_is_written_on_the_ticket(at_contacts):
    """Visas skambutis: numeris → perklausimas → „Taip“ → įrašyta tikete"""
    c = _registered_call(at_contacts)
    assert f"Užrašiau {NEW}" in c.say(f"Skambinkite kitu numeriu {NEW}")
    assert NEW not in (_details(c.state.ticket.ticket_id) or "")
    assert "Užsirašiau" in c.say("Taip")
    assert NEW in _details(c.state.ticket.ticket_id)
    assert c.state.ticket.contact_phone == NEW


def test_a_hang_up_at_the_read_back_reaches_the_ticket(at_contacts):
    """Visas skambutis: perklausimas → padėtas ragelis → „nepatvirtintas“ tikete"""
    c = _registered_call(at_contacts)
    c.say(f"Skambinkite kitu numeriu {NEW}")
    c.session.end_session("client_closed")
    details = _details(c.state.ticket.ticket_id)
    assert NEW in details and "nepatvirtint" in details
