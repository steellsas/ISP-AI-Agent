"""Infra guards: the database itself — connection, schema shape, seeded state,
in-place reset. (2026-08-05 cleanup: the DB used to be tested only implicitly
through tools; this file owns the layer.)

Run: pytest tests/test_db.py -v
"""

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
