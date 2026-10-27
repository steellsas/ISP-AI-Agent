"""Infra guards: the database itself — connection, schema shape, seeded state,
in-place reset. (2026-08-05 cleanup: the DB used to be tested only implicitly
through tools; this file owns the layer.)

Run: pytest tests/tools/test_db.py -v
"""

FUNCTION = "Duomenų bazė"

# The demo/eval flows and the dashboard's DB-reset button all depend on these
# tables existing exactly under these names.
_CORE_TABLES = {
    "customers",
    "addresses",
    "customer_equipment",
    "tickets",
    "conversations",
    "streets",
    "switches",
    "ports",
    "ip_assignments",
    "area_outages",
}


class TestSchema:
    def test_connection_and_core_tables(self, db_connection):
        with db_connection.cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
        assert _CORE_TABLES <= tables, f"missing: {_CORE_TABLES - tables}"

    def test_seeded_state_present(self, db_connection):
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM customers")
            assert dict(cur.fetchone())["n"] >= 10
            cur.execute("SELECT COUNT(*) AS n FROM ports")
            assert dict(cur.fetchone())["n"] > 0


class TestInPlaceReset:
    def test_reset_restores_seed_and_keeps_connections_valid(self, db_connection):
        """admin.reset_db drops + re-seeds WITHOUT unlinking the file (a held
        file is WinError 32 on Windows) — existing connections must survive."""
        from app.admin import reset_db

        result = reset_db()
        assert result["reset"] is True and result["customers"] >= 10
        # The fixture's connection still works against the re-created schema.
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM customers")
            assert dict(cur.fetchone())["n"] == result["customers"]

    def test_reset_keeps_the_call_records(self, db_connection):
        """The archive lists past calls from `conversations`; a scenario's ▶ resets the DB
        before every call, and the reset used to wipe the previous calls (2026-10-27)."""
        import sqlite3

        from agent.db_path import database_path
        from app.admin import reset_db

        conn = sqlite3.connect(database_path())
        conn.execute(
            "INSERT INTO tickets (ticket_id, customer_id, ticket_type, summary)"
            " VALUES ('TKT-GONE', 'CUST001', 'fault_technician', 'x')"
        )
        conn.execute(
            "INSERT INTO conversations (conversation_id, session_id, messages, outcome, ticket_id)"
            " VALUES ('C-KEEP', 'S-KEEP', '[]', 'ticket', 'TKT-GONE')"
        )
        conn.commit()
        conn.close()

        reset_db()

        conn = sqlite3.connect(database_path())
        try:
            kept = conn.execute(
                "SELECT session_id, outcome, ticket_id FROM conversations"
                " WHERE conversation_id = 'C-KEEP'"
            ).fetchone()
            ticket = conn.execute("SELECT 1 FROM tickets WHERE ticket_id = 'TKT-GONE'").fetchone()
        finally:
            conn.close()
        assert kept == ("S-KEEP", "ticket", "TKT-GONE")
        assert ticket is None  # the demo data itself is reset
