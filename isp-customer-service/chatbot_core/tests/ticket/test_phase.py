"""Visa fazė — from the engine's decision to register to the goodbye, through the real graph:
the conclusion said, the contacts collected, the ticket written with its type and its reason,
the details read back to the caller, the call closed."""

import sqlite3

from agent.db_path import database_path

FUNCTION = "Visa fazė"


def _row(ticket_id):
    conn = sqlite3.connect(database_path())
    try:
        return conn.execute(
            "SELECT customer_id, ticket_type, problem_type, status, details FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
    finally:
        conn.close()


def test_a_dead_router_ends_in_a_written_ticket(at_contacts):
    """Miręs routeris → kontaktai → įrašytas tiketas → atsisveikinimas"""
    c = at_contacts()
    assert "neišspręsime" in c.replies[-1] and "Registruoju meistrą" in c.replies[-1]
    c.say("Taip")
    told = c.say("Po pietų")
    ticket = c.state.ticket.ticket_id
    assert ticket and "Skambinsime +370 600 12345, po pietų" in told
    customer, kind, problem, status, details = _row(ticket)
    assert (customer, kind, problem, status) == (
        "CUST001",
        "equipment_replacement",
        "internet_down",
        "open",
    )
    assert "Registruota, nes:" in details  # the reason travels to the technician
    c.say("Ne, ačiū")
    assert (
        c.state.closing.closed_reason == "registered" and c.rule == "closing.goodbye_after_ticket"
    )


def test_another_number_is_read_back(at_contacts):
    """Kitas numeris — perskaitomas atgal"""
    c = at_contacts()
    c.say("Ne, kitu numeriu: 861234567")
    told = c.say("Bet kada")
    assert "Skambinsime 861234567, bet kada" in told


def test_a_billing_request_is_written_for_the_responsible_person(call):
    """Sąskaitos klausimas → tiketas atsakingam žmogui"""
    c = call("+37060020112")
    for text in ("Skambinu dėl sąskaitos", "Taip", "Paulius", "Taip", "Bet kada"):
        c.say(text)
    ticket = c.state.ticket.ticket_id
    assert ticket and _row(ticket)[1] == "billing_request"
    assert "diagnose_connection" not in c.tools
